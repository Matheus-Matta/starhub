"""Galeria sem foto repetida: a migracao que juntou as antigas e quem grava as novas."""

import importlib

import pytest
from django.apps import apps
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.core.models import ExternalReference
from apps.loja.models import MidiaProduto, VarianteProduto
from apps.loja.services.midias import sincronizar_midias, url_da_foto
from apps.loja.services.variantes import criar_produto

migracao = importlib.import_module("apps.loja.migrations.0030_juntar_fotos_repetidas")
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(conta, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def arquivo(nome, conteudo):
    return default_storage.url(default_storage.save(f"produtos/{nome}", ContentFile(conteudo)))


def foto(variante, url, posicao=0):
    return MidiaProduto.objects.create(produto=variante.produto, variante=variante, url=url,
                                       posicao=posicao)


def vincular(midia, externo, **metadata):
    return ExternalReference.objects.create(
        platform="shopify", entity_type="midias", object_id=str(midia.pk),
        external_id=externo, metadata=metadata)


def test_junta_as_repetidas_sem_apagar_arquivo_e_volta():
    """Produto com a mesma foto baixada 3 vezes por webhooks simultaneos."""
    variante = criar_produto("Roupeiro", sku="R1").variante_padrao
    urls = [arquivo(f"{n}.png", b"igual") for n in "abc"]
    midias = [foto(variante, url, n) for n, url in enumerate(urls)]
    outra = foto(variante, arquivo("d.png", b"outra"), 3)
    vincular(midias[2], "gid://1", shopify_src="https://cdn.shopify.com/a.png")

    migracao.juntar(apps, None)

    ficaram = list(variante.midias.order_by("posicao"))
    assert [m.pk for m in ficaram] == [midias[2].pk, outra.pk], "fica a ligada a loja"
    assert ficaram[0].posicao == 0, "a capa continua na frente"
    assert all(default_storage.exists(f"produtos/{n}.png") for n in "abcd")

    migracao.recriar(apps, None)
    assert sorted(variante.midias.values_list("url", flat=True)) == sorted([*urls, outra.url])


def test_vinculos_da_repetida_passam_para_a_que_fica():
    """Vinculo sem linha faz o proximo update apagar a foto do Shopify; e `enviado_src`
    de outra url seria lido como foto trocada (apaga e manda de novo)."""
    variante = criar_produto("Roupeiro", sku="R1").variante_padrao
    fica = foto(variante, arquivo("a.png", b"igual"), 0)
    sai = foto(variante, arquivo("b.png", b"igual"), 1)
    vincular(fica, "gid://1", enviado_src=fica.url)
    vincular(sai, "gid://2", enviado_src="https://hub.test" + sai.url)

    migracao.juntar(apps, None)

    vinculo = ExternalReference.objects.get(external_id="gid://2")
    assert vinculo.object_id == str(fica.pk)
    assert vinculo.metadata["enviado_src"] == fica.url


def test_mesma_foto_em_duas_variantes_fica_nas_duas_com_a_mesma_url():
    """Agrupar simples trazia 10 tamanhos com as mesmas fotos: cada variante precisa da
    sua, mas as lojas e a API Woo recebem uma so."""
    produto = criar_produto("Sofa", sku="S1")
    azul = VarianteProduto.objects.create(produto=produto, titulo="Azul", posicao=1)
    a = foto(produto.variante_padrao, arquivo("a.png", b"igual"))
    b = foto(azul, arquivo("b.png", b"igual"))

    migracao.juntar(apps, None)

    b.refresh_from_db()
    assert b.url == a.url and produto.midias.count() == 2
    assert [i["src"] for i in produto.imagens] == [a.url]


def test_url_absoluta_ou_sem_id_do_mesmo_arquivo_mantem_a_linha():
    """O ERP devolve a URL inteira e as vezes sem id: a linha nova perdia o vinculo e a
    foto subia de novo para as lojas."""
    variante = criar_produto("Mesa", sku="M1").variante_padrao
    url = arquivo("a.png", b"mesa")
    midia = foto(variante, url)

    sincronizar_midias(variante, [{"src": "https://hub.test" + url}, {"src": url}])

    unica = variante.midias.get()
    assert (unica.pk, unica.url) == (midia.pk, url)


def test_foto_baixada_de_novo_reaproveita_a_do_produto():
    variante = criar_produto("Mesa", sku="M1").variante_padrao
    midia = foto(variante, arquivo("a.png", b"mesa"))
    nova = arquivo("b.png", b"mesa")
    assert url_da_foto(variante.produto, nova) == midia.url
    diferente = arquivo("c.png", b"mes4")
    assert url_da_foto(variante.produto, diferente) == diferente
