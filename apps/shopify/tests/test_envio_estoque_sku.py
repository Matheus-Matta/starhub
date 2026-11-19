"""Estoque para o Shopify com vinculo velho: a variante que sumiu e achada pelo SKU.

Antes a baixa/entrada falhava ("a variante nao existe mais na loja") ate alguem
sincronizar o produto.
"""

import pytest

from apps.core.models import ExternalReference
from apps.shopify.cliente import ShopifyErro
from apps.shopify.tests.test_envio_estoque import (
    ITEM_GID,
    LOCAL,
    OK,
    VARIANTE_GID,
    _enviador,
    _variante,
)


@pytest.mark.django_db
def test_variante_que_sumiu_da_loja_recebe_o_estoque_pela_variante_do_mesmo_sku(conta):
    """Vinculo velho: a baixa falhava ate alguem sincronizar o produto."""
    variante = _variante()
    variante.sku = "MESA-1"
    variante.save()
    nova = {"id": "gid://shopify/ProductVariant/99", "inventoryItem": {"id": ITEM_GID}}
    enviador = _enviador(conta, {
        "inventorySetQuantities": OK, "productVariants(": {"productVariants": {"nodes": [nova]}},
        "productVariant(": {"productVariant": None}, "location": LOCAL,
    })

    enviador.atualizar(variante, VARIANTE_GID)

    busca = next(v for q, v in enviador.cliente.chamadas if "productVariants(" in q)
    assert busca == {"q": 'sku:"MESA-1"'}
    assert enviador.cliente.chamadas[-1][1]["input"]["quantities"][0]["inventoryItemId"] == ITEM_GID
    referencia = ExternalReference.objects.get(object_id=str(variante.pk))
    assert referencia.external_id == "gid://shopify/ProductVariant/99"


@pytest.mark.django_db
def test_sku_repetido_na_loja_nao_escolhe_variante(conta):
    variante = _variante()
    variante.sku = "MESA-1"
    variante.save()
    duas = [{"id": f"gid://shopify/ProductVariant/{n}", "inventoryItem": {"id": ITEM_GID}}
            for n in (98, 99)]
    enviador = _enviador(conta, {
        "productVariants(": {"productVariants": {"nodes": duas}},
        "productVariant(": {"productVariant": None}, "location": LOCAL,
    })

    with pytest.raises(ShopifyErro, match="SKU repetido"):
        enviador.atualizar(variante, VARIANTE_GID)


@pytest.mark.django_db
def test_item_guardado_de_variante_apagada_confere_de_novo_e_reenvia(conta):
    variante = _variante(metadata={"inventory_item_id": "gid://shopify/InventoryItem/velho"})
    respostas = iter([
        {"inventorySetQuantities": {"userErrors": [{"field": ["x"], "message": "not found"}]}},
        {"productVariant": {"inventoryItem": {"id": ITEM_GID}}},
        OK,
    ])
    enviador = _enviador(conta, {"location": LOCAL})
    original = enviador.cliente.graphql

    def graphql(query, variables=None):
        if "location" in query:
            return original(query, variables)
        enviador.cliente.chamadas.append((query, variables))
        return next(respostas)

    enviador.cliente.graphql = graphql
    enviador.atualizar(variante, VARIANTE_GID)

    assert enviador.cliente.chamadas[-1][1]["input"]["quantities"][0]["inventoryItemId"] == ITEM_GID
