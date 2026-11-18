"""Foto apagada ou trocada no hub sai da loja Shopify.

O update so acrescentava midia: o produto com 6 fotos no hub reduzido a 2 continuava
com 6 na loja, e a foto trocada (mesma linha, URL nova) nem era reenviada.
Sai so midia com vinculo: foto cadastrada direto na loja e sem vinculo fica.
"""

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import MidiaProduto
from apps.shopify.tests.test_envio_midias import _chamada, _respostas_update, _vincular_variante
from apps.shopify.tests.test_envio_produtos import PRODUTO_GID, _enviador, _simples

APAGOU = {"fileDelete": {"fileDelete": {"deletedFileIds": [], "userErrors": []}}}


def _gid(n):
    return f"gid://shopify/MediaImage/{n}"


def _foto(produto, n):
    midia = MidiaProduto.objects.create(produto=produto, url=f"https://hub.test/{n}.png",
                                        posicao=n)
    ExternalReference.objects.create(
        platform="shopify", entity_type="midias", object_id=str(midia.pk),
        external_id=_gid(n), metadata={"enviado_src": midia.url})
    return midia


def _midias_vinculadas():
    return sorted(ExternalReference.objects.filter(entity_type="midias")
                  .values_list("external_id", flat=True))


@pytest.mark.django_db
def test_fotos_apagadas_no_hub_saem_da_loja(conta):
    produto, variante = _simples()
    _vincular_variante(variante)
    fotos = [_foto(produto, n) for n in range(1, 7)]
    for midia in fotos[2:]:
        midia.delete()
    enviador = _enviador(conta, {**_respostas_update(1, 2, 3, 4, 5, 6, 99), **APAGOU})

    enviador.atualizar(produto, PRODUTO_GID)

    assert "media" not in _chamada(enviador, "productUpdate")
    assert _chamada(enviador, "fileDelete") == {"fileIds": [_gid(n) for n in (3, 4, 5, 6)]}
    assert _midias_vinculadas() == [_gid(1), _gid(2)]


@pytest.mark.django_db
def test_foto_trocada_no_hub_vai_nova_e_a_antiga_sai(conta):
    produto, variante = _simples()
    _vincular_variante(variante)
    midia = _foto(produto, 1)
    midia.url = "https://hub.test/nova.png"
    midia.save()
    enviador = _enviador(conta, {**_respostas_update(1, 2), **APAGOU})

    enviador.atualizar(produto, PRODUTO_GID)

    assert [m["originalSource"] for m in _chamada(enviador, "productUpdate")["media"]] == [
        "https://hub.test/nova.png"]
    assert _chamada(enviador, "fileDelete") == {"fileIds": [_gid(1)]}
    assert _midias_vinculadas() == [_gid(2)]


@pytest.mark.django_db
def test_nada_apagado_nao_chama_o_file_delete(conta):
    produto, variante = _simples()
    _vincular_variante(variante)
    _foto(produto, 1)
    enviador = _enviador(conta, _respostas_update(1))

    enviador.atualizar(produto, PRODUTO_GID)

    assert not any("fileDelete" in q for q, _ in enviador.cliente.chamadas)
