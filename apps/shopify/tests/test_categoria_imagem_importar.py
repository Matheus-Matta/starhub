"""Importacao da imagem da colecao do Shopify para o MEDIA do hub, sem duplicar.

Antes a categoria ficava so com o link da CDN: a foto sumia do hub quando a loja a
trocava ou apagava, e o hub dependia da CDN do Shopify para mostrar a propria imagem.
"""

from unittest.mock import patch
from urllib.error import URLError

import pytest

from apps.core.models import ExternalReference
from apps.integracoes.models import ExecucaoIntegracao
from apps.loja.models import Categoria
from apps.shopify import atualizar, recursos
from apps.shopify.tasks import sincronizar_shopify
from apps.shopify.tests.test_categoria_imagem import _configuracao, _enviar, _webhook
from apps.shopify.tests.test_imagens_webhook import PNG, RespostaImagem

GID = "gid://shopify/Collection/3"
CDN = "https://cdn.shopify.com/s/files/1/collections/sala.png"


def _colecao(url=CDN + "?v=1", alt="Sala"):
    return {"id": GID, "title": "Sala", "handle": "sala", "descriptionHtml": "",
            "image": {"url": url, "altText": alt} if url else None}


def _baixando(funcao, *args, efeito=None):
    with patch("urllib.request.urlopen", return_value=RespostaImagem(PNG),
               side_effect=efeito) as baixar:
        funcao(*args)
    return baixar


def _categoria():
    return Categoria.objects.get(slug="sala")


def _metadata():
    return ExternalReference.objects.get(entity_type="categorias").metadata


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return settings.MEDIA_URL


@pytest.mark.django_db
def test_importar_colecao_com_imagem_baixa_e_grava_url_local(conta, media):
    """A categoria nova fica com o arquivo no MEDIA do hub, e o vinculo com a origem."""
    baixar = _baixando(recursos.categoria, _colecao())

    assert baixar.call_count == 1
    imagem = _categoria().imagem
    assert imagem["src"].startswith(f"{media}categorias/") and imagem["alt"] == "Sala"
    assert _metadata()["imagem_origem"] == "cdn.shopify.com/s/files/1/collections/sala.png"
    assert not _categoria().metadados, "dado do Shopify fica no vinculo, nao na categoria"


@pytest.mark.django_db
def test_mesma_imagem_com_outra_versao_nao_baixa_de_novo(conta, media):
    """A sincronizacao e o webhook devolvem a mesma foto com ?v= diferente."""
    _baixando(recursos.categoria, _colecao())
    antes = _categoria().imagem

    baixar = _baixando(atualizar.categoria, _colecao(CDN + "?v=2"))

    assert baixar.call_count == 0
    assert _categoria().imagem == antes


@pytest.mark.django_db
def test_imagem_trocada_no_shopify_baixa_a_nova(conta, media):
    _baixando(recursos.categoria, _colecao())
    antes = _categoria().imagem["src"]

    baixar = _baixando(atualizar.categoria, _colecao(CDN.replace("sala.png", "sala2.png")))

    assert baixar.call_count == 1
    depois = _categoria().imagem["src"]
    assert depois != antes and depois.startswith(f"{media}categorias/")


@pytest.mark.django_db
def test_colecao_sem_imagem_nao_apaga_a_imagem_do_hub(conta, media):
    """Decisao: o hub nao perde a foto porque a loja ficou sem; apagar e manual no hub."""
    _baixando(recursos.categoria, _colecao())
    antes = _categoria().imagem

    _baixando(atualizar.categoria, _colecao(url=None))

    assert _categoria().imagem == antes


@pytest.mark.django_db
def test_eco_da_imagem_enviada_pelo_hub_nao_baixa(conta, media):
    configuracao = _configuracao(conta)
    hub = "https://hub.exemplo.com/media/categorias/sala.png"
    categoria = Categoria.objects.create(nome="Sala", slug="sala", imagem={"src": hub})
    _enviar(configuracao, "create", categoria)

    baixar = _baixando(_webhook, configuracao, CDN + "?v=1")

    assert baixar.call_count == 0
    assert _categoria().imagem["src"] == hub


@pytest.mark.django_db
def test_imagem_baixada_nao_volta_para_o_shopify(conta, media):
    """A foto local veio da loja: mandar de novo faria o Shopify baixar uma copia."""
    configuracao = _configuracao(conta)
    configuracao.url_webhook = "https://hub.exemplo.com/shopify/webhooks/"
    configuracao.save()
    _baixando(recursos.categoria, _colecao())
    categoria = _categoria()

    [depois] = _enviar(configuracao, "update", categoria)
    nova = {"src": "/media/categorias/outra.png", "alt": "Outra"}
    categoria.imagem = nova
    categoria.save()
    [trocada] = _enviar(configuracao, "update", categoria)

    assert "image" not in depois
    # A URL local vira publica pelo endereco do hub: sem isso o teste acima passaria
    # so porque nenhuma URL local seria enviada.
    assert trocada["image"]["src"] == "https://hub.exemplo.com/media/categorias/outra.png"


@pytest.mark.django_db
def test_falha_no_download_nao_derruba_a_categoria_e_aparece_na_execucao(
    conta, media, monkeypatch
):
    configuracao = _configuracao(conta)
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR,
    )

    def sincronizar(_configuracao, _progresso):
        recursos.categoria(_colecao())
        return "1 itens encontrados."

    monkeypatch.setattr("apps.shopify.tasks.sincronizar_loja", sincronizar)
    _baixando(sincronizar_shopify.run, str(execucao.pk), efeito=URLError("timeout"))

    execucao.refresh_from_db()
    assert execucao.status == ExecucaoIntegracao.Status.CONCLUIDA_COM_FALHAS
    assert _categoria().imagem in (None, {})
    assert "sala.png" in execucao.mensagem and "imagem" in execucao.mensagem.lower()
    assert "imagem_origem" not in _metadata(), "a proxima sincronizacao tenta de novo"
