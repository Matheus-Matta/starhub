"""Id guardado que existe na loja, mas e de OUTRO produto: o SKU acha o certo.

So o "Product does not exist" fazia o hub procurar pelo SKU. Id que apontava para um
produto que existe, mas e outro (vinculo trocado), fazia o hub gravar nome, descricao
e preco no produto errado da loja, para sempre. Antes de alterar, o hub confere os SKUs
do produto do id; nenhum bate -> busca pelo SKU, pega o id certo e altera esse.
"""

import pytest

from apps.shopify.tests.test_envio_produto_religar import (
    NOVO,
    VELHO,
    _ok,
    _preparar,
    _sku,
    _vinculo_do_produto,
)
from apps.shopify.tests.test_envio_produtos_atualizar import BULK_UPDATE


def _da_loja(*skus):
    return {"product": {"id": VELHO, "variants": {"nodes": [{"sku": s} for s in skus]}}}


def _alterados(enviador):
    return [v["product"]["id"] for q, v in enviador.cliente.chamadas if "productUpdate" in q]


def _buscou(enviador):
    return any("productVariants(" in q for q, _ in enviador.cliente.chamadas)


@pytest.mark.django_db
def test_id_de_outro_produto_busca_pelo_sku_e_altera_o_certo(conta):
    produto, enviador = _preparar(conta, {
        "product(id:": _da_loja("CADEIRA-9"), "productVariants(": _sku(NOVO),
        "productUpdate": _ok(NOVO), "productVariantsBulkUpdate": BULK_UPDATE})

    enviador.atualizar(produto, VELHO)

    assert _alterados(enviador) == [NOVO], "o produto errado da loja nao pode ser alterado"
    assert _vinculo_do_produto(produto) == [NOVO]


@pytest.mark.django_db
def test_sku_que_bate_altera_pelo_id_sem_buscar(conta):
    produto, enviador = _preparar(conta, {
        "product(id:": _da_loja("MESA-1"), "productUpdate": _ok(VELHO),
        "productVariantsBulkUpdate": BULK_UPDATE})

    enviador.atualizar(produto, VELHO)

    assert _alterados(enviador) == [VELHO] and not _buscou(enviador)


@pytest.mark.django_db
def test_sku_trocado_no_hub_sem_outro_produto_na_loja_altera_pelo_id(conta):
    """2822 -> 2822A no hub: a loja ainda tem o antigo, e e o update que leva o novo."""
    produto, enviador = _preparar(conta, {
        "product(id:": _da_loja("SKU-ANTIGO"), "productVariants(": _sku(),
        "productUpdate": _ok(VELHO), "productVariantsBulkUpdate": BULK_UPDATE})

    enviador.atualizar(produto, VELHO)

    assert _alterados(enviador) == [VELHO]
    assert _vinculo_do_produto(produto) == [VELHO]


@pytest.mark.django_db
def test_produto_da_loja_sem_sku_segue_pelo_id(conta):
    produto, enviador = _preparar(conta, {
        "product(id:": _da_loja(""), "productUpdate": _ok(VELHO),
        "productVariantsBulkUpdate": BULK_UPDATE})

    enviador.atualizar(produto, VELHO)

    assert _alterados(enviador) == [VELHO] and not _buscou(enviador)


@pytest.mark.django_db
def test_sku_em_produto_de_outro_produto_do_hub_nao_rouba_e_segue_pelo_id(conta):
    from apps.core.models import ExternalReference

    produto, enviador = _preparar(conta, {
        "product(id:": _da_loja("CADEIRA-9"), "productVariants(": _sku(NOVO),
        "productUpdate": _ok(VELHO), "productVariantsBulkUpdate": BULK_UPDATE})
    ExternalReference.objects.create(platform="shopify", entity_type="produtos",
                                     object_id="999999", external_id=NOVO)

    enviador.atualizar(produto, VELHO)

    assert _alterados(enviador) == [VELHO]
    assert _vinculo_do_produto(produto) == [VELHO]
