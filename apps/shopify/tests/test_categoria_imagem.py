"""Imagem da categoria no Shopify: vai so quando a URL do hub mudou, e o eco nao a troca.

Mandar `image.src` a cada update fazia o Shopify baixar a mesma foto de novo; e o
webhook collections/update, que volta com a URL da CDN, sobrescrevia a imagem do hub.
"""

from unittest.mock import patch

import pytest

from apps.core.models import ExternalReference
from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Categoria
from apps.shopify.tests.test_envio_produtos import ClienteFalso
from apps.shopify.tests.test_imagens_webhook import PNG, RespostaImagem
from apps.shopify.webhooks import processar_webhook

GID = "gid://shopify/Collection/3"
HUB = "https://hub.exemplo.com/media/categorias/sala.png"
CDN = "https://cdn.shopify.com/s/files/1/collections/sala.png?v=1"
RESPOSTAS = {
    "collectionCreate": {"collectionCreate": {"collection": {"id": GID}, "userErrors": []}},
    "collectionUpdate": {"collectionUpdate": {"collection": {"id": GID}, "userErrors": []}},
}


def _configuracao(conta):
    matriz = permissoes.matriz_vazia()
    for operacao in ("create", "update"):
        matriz["enviar"]["categorias"][operacao] = True
        matriz["receber"]["categorias"][operacao] = True
    return ConfiguracaoIntegracao.objects.create(
        account=conta, plataforma="shopify", permissoes=matriz
    )


def _enviar(configuracao, operacao, categoria):
    from apps.shopify.envio.marketplace import ShopifyMarketplace

    enviador = ShopifyMarketplace(configuracao).enviador("categorias")
    enviador._cliente = ClienteFalso(RESPOSTAS)
    enviador.enviar(operacao, categoria.pk)
    return [v["colecao"] for _q, v in enviador._cliente.chamadas]


def _metadata():
    return ExternalReference.objects.get(entity_type="categorias").metadata


@pytest.mark.django_db
def test_imagem_so_vai_quando_a_url_do_hub_muda(conta):
    """Update sem troca de foto nao manda `image`; foto nova vai uma vez."""
    configuracao = _configuracao(conta)
    categoria = Categoria.objects.create(nome="Sala", slug="sala", imagem={"src": HUB})

    [criada] = _enviar(configuracao, "create", categoria)
    [igual] = _enviar(configuracao, "update", categoria)
    categoria.imagem = {"src": HUB.replace("sala", "sala2"), "alt": "Sala"}
    categoria.save()
    [trocada] = _enviar(configuracao, "update", categoria)

    assert criada["image"]["src"] == HUB
    assert "image" not in igual
    assert trocada["image"] == {"src": HUB.replace("sala", "sala2"), "altText": "Sala"}
    assert _metadata()["imagem_enviada"] == HUB.replace("sala", "sala2")
    categoria.refresh_from_db()
    assert not categoria.metadados, "dado do Shopify fica no vinculo, nao na categoria"


def _webhook(configuracao, src):
    processar_webhook(configuracao, "categorias", "update", {
        "id": 3, "title": "Sala", "body_html": "", "image": {"src": src, "alt": ""},
    }, lambda *_: None)


@pytest.mark.django_db
def test_eco_da_categoria_nao_troca_a_imagem_do_hub_nem_reenvia(conta):
    """A CDN que volta e a foto que o hub mandou: o hub fica com a URL dele."""
    configuracao = _configuracao(conta)
    categoria = Categoria.objects.create(nome="Sala", slug="sala", imagem={"src": HUB})
    _enviar(configuracao, "create", categoria)

    _webhook(configuracao, CDN)
    _webhook(configuracao, CDN)
    categoria.refresh_from_db()
    [depois] = _enviar(configuracao, "update", categoria)

    assert categoria.imagem["src"] == HUB
    assert _metadata() == {"imagem_enviada": HUB, "imagem_shopify": CDN}
    assert "image" not in depois


@pytest.mark.django_db
def test_imagem_trocada_no_shopify_entra_no_hub_e_nao_volta(conta, settings, tmp_path):
    """Foto nova cadastrada na loja vale no hub (baixada); ja e da loja, nao e reenviada."""
    settings.MEDIA_ROOT = tmp_path
    configuracao = _configuracao(conta)
    configuracao.url_webhook = "https://hub.exemplo.com/shopify/webhooks/"
    configuracao.save()
    categoria = Categoria.objects.create(nome="Sala", slug="sala", imagem={"src": HUB})
    _enviar(configuracao, "create", categoria)
    _webhook(configuracao, CDN)
    nova = CDN.replace("sala.png", "sala-nova.png")

    with patch("urllib.request.urlopen", return_value=RespostaImagem(PNG)):
        _webhook(configuracao, nova)
    categoria.refresh_from_db()
    [depois] = _enviar(configuracao, "update", categoria)

    assert categoria.imagem["src"].startswith(f"{settings.MEDIA_URL}categorias/")
    assert "image" not in depois
