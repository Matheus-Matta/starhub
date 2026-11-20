"""Fotos quando o vinculo do produto e refeito pelo SKU: casa pela referencia, sem duplicar.

Religado a outro produto da loja (id velho sumiu ou era de outro produto), o hub
esquecia os vinculos das fotos e mandava a galeria inteira para o produto achado, que ja
tinha as mesmas fotos: ficava tudo em dobro. Agora cada foto do hub procura a sua na
loja pela referencia que o vinculo guardava (URL da CDN sem ?v=, ou o nome do arquivo
enviado); casou, so religa; foto da loja que nao casou sai; foto do hub sem par vai.
"""

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import MidiaProduto
from apps.shopify.tests.test_envio_produto_religar import (
    NOVO,
    VELHO,
    _ok,
    _preparar,
    _sku,
)
from apps.shopify.tests.test_envio_produtos_atualizar import BULK_UPDATE

CDN = "https://cdn.shopify.com/s/files/1/0001/files/"
HUB = "https://hub.test/media/produtos/"
APAGOU = {"fileDelete": {"deletedFileIds": [], "userErrors": []}}


def _foto(produto, url, n, **metadata):
    midia = MidiaProduto.objects.create(produto=produto, url=url, posicao=n)
    ExternalReference.objects.create(platform="shopify", entity_type="midias",
                                     object_id=str(midia.pk), external_id=f"velha-{n}",
                                     metadata=metadata)
    return midia


def _da_loja(*fotos):
    return {"node": {"id": NOVO, "media": {"nodes": [
        {"id": f"gid://shopify/MediaImage/{n}", "image": {"url": url}} for n, url in fotos]}}}


def _respostas(*fotos):
    # "node(id:" antes de "product(id:": a ordem decide no cliente falso.
    return {"node(id:": _da_loja(*fotos), "product(id:": {"product": None},
            "productVariants(": _sku(NOVO), "productUpdate": [
                {"productUpdate": {"product": None, "userErrors": [
                    {"field": ["id"], "message": "Product does not exist"}]}},
                _ok(NOVO)],
            "productVariantsBulkUpdate": BULK_UPDATE, "fileDelete": APAGOU}


def _vinculo(midia):
    return ExternalReference.objects.get(entity_type="midias", object_id=str(midia.pk))


def _chamada(enviador, raiz):
    return [v for q, v in enviador.cliente.chamadas if raiz in q]


@pytest.mark.django_db
def test_fotos_que_ja_estao_no_produto_achado_so_religam_e_a_sobra_sai(conta):
    produto, enviador = _preparar(conta, _respostas(
        (1, f"{CDN}sofa-frente.jpg?v=99"), (2, f"{CDN}de29dba67def463ea_a1b2.png?v=5"),
        (3, f"{CDN}foto-que-o-hub-nao-tem.jpg?v=1")))
    importada = _foto(produto, f"{HUB}copia-local.jpg", 0,
                      shopify_src=f"{CDN}sofa-frente.jpg?v=12")
    enviada = _foto(produto, f"{HUB}de29dba67def463ea.png", 1,
                    enviado_src=f"{HUB}de29dba67def463ea.png")

    enviador.atualizar(produto, VELHO)

    assert _vinculo(importada).external_id == "gid://shopify/MediaImage/1"
    assert _vinculo(enviada).external_id == "gid://shopify/MediaImage/2"
    assert all("media" not in v for v in _chamada(enviador, "productUpdate")), "duplicaria"
    assert _chamada(enviador, "fileDelete") == [{"fileIds": ["gid://shopify/MediaImage/3"]}]


@pytest.mark.django_db
def test_sem_nenhuma_referencia_igual_apaga_as_da_loja_e_manda_as_do_hub(conta):
    produto, enviador = _preparar(conta, _respostas((7, f"{CDN}outra.jpg?v=1")))
    _foto(produto, f"{HUB}mesa.png", 0, enviado_src=f"{HUB}mesa.png")

    enviador.atualizar(produto, VELHO)

    assert _chamada(enviador, "fileDelete")[0] == {"fileIds": ["gid://shopify/MediaImage/7"]}
    [segundo] = [v for v in _chamada(enviador, "productUpdate") if v["product"]["id"] == NOVO]
    assert [m["originalSource"] for m in segundo["media"]] == [f"{HUB}mesa.png"]
