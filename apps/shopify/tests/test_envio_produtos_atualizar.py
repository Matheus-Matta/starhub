"""Update de produto no Shopify: productUpdate + variantes em lote, nunca productSet.

productSet apaga da loja o que nao vai na lista (colecoes, midias, variantes): usado
num update, cada edicao no hub arrancaria imagens e colecoes do produto na loja.
"""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Produto, VarianteProduto
from apps.shopify.tests.test_envio_produtos import PRODUTO_GID, _enviador, _simples

UPDATE = {"productUpdate": {"product": {"id": PRODUTO_GID}, "userErrors": []}}
BULK_UPDATE = {"productVariantsBulkUpdate": {"productVariants": [], "userErrors": []}}
BULK_CREATE = {"productVariantsBulkCreate": {"productVariants": [
    {"id": "gid://shopify/ProductVariant/2", "inventoryItem": {"id": "gid://shopify/InventoryItem/2"}}
], "userErrors": []}}
LOCAL = {"location": {"id": "gid://shopify/Location/1"}}


def _vincular(variante, numero):
    ExternalReference.objects.create(
        platform="shopify", entity_type="variantes", object_id=str(variante.pk),
        external_id=f"gid://shopify/ProductVariant/{numero}", external_parent_id=PRODUTO_GID,
    )


def _respostas():
    return {
        "productVariantsBulkUpdate": BULK_UPDATE, "productVariantsBulkCreate": BULK_CREATE,
        "productUpdate": UPDATE, "location": LOCAL,
    }


def _chamada(enviador, raiz):
    return next(v for q, v in enviador.cliente.chamadas if raiz in q)


@pytest.mark.django_db
def test_atualizar_usa_product_update_so_com_os_campos_do_produto(conta):
    """Nada de productSet nem de colecoes/midias/metafields: o que so existe na loja fica."""
    produto, variante = _simples()
    produto.status = Produto.Status.RASCUNHO
    produto.save()
    _vincular(variante, 1)
    enviador = _enviador(conta, _respostas())

    enviador.atualizar(produto, "900")

    queries = [q for q, _ in enviador.cliente.chamadas]
    assert not any("productSet" in q for q in queries)
    assert not any("productVariantsBulkCreate" in q for q in queries)
    entrada = _chamada(enviador, "productUpdate")["product"]
    assert entrada == {
        "id": PRODUTO_GID, "title": "Mesa", "descriptionHtml": "<p>Mesa boa</p>",
        "vendor": "Moveis FDC", "status": "DRAFT", "tags": ["sala"],
    }
    for _, variaveis in enviador.cliente.chamadas:
        texto = str(variaveis)
        assert "collections" not in texto and "files" not in texto and "media" not in texto


@pytest.mark.django_db
def test_atualizar_manda_preco_e_sku_da_variante_vinculada_em_lote(conta):
    """Variante vinculada vai pelo id; o sku fica em inventoryItem (nao existe no topo)."""
    produto, variante = _simples()
    _vincular(variante, 1)
    enviador = _enviador(conta, _respostas())

    enviador.atualizar(produto, PRODUTO_GID)

    variaveis = _chamada(enviador, "productVariantsBulkUpdate")
    assert variaveis["productId"] == PRODUTO_GID
    [enviada] = variaveis["variants"]
    assert enviada["id"] == "gid://shopify/ProductVariant/1"
    assert enviada["price"] == "80.00"
    assert enviada["compareAtPrice"] == "100.00"
    assert enviada["inventoryItem"] == {
        "sku": "MESA-1", "tracked": True, "requiresShipping": True,
    }
    assert "sku" not in enviada
    assert "inventoryQuantities" not in enviada


@pytest.mark.django_db
def test_variante_nova_do_hub_e_criada_e_vinculada_sem_apagar_as_da_loja(conta):
    """Variante sem vinculo e criada; a estrategia preserva a variante que ja existe."""
    produto = Produto.objects.create(nome="Sofa", tipo=Produto.Tipo.VARIAVEL)
    antiga = VarianteProduto.objects.create(produto=produto, titulo="Bege", price=Decimal("10"))
    nova = VarianteProduto.objects.create(
        produto=produto, titulo="Prata", price=Decimal("12"), inventory_quantity=4, posicao=1
    )
    _vincular(antiga, 1)
    enviador = _enviador(conta, _respostas())

    enviador.atualizar(produto, PRODUTO_GID)

    atualizadas = _chamada(enviador, "productVariantsBulkUpdate")["variants"]
    assert [v["id"] for v in atualizadas] == ["gid://shopify/ProductVariant/1"]
    variaveis = _chamada(enviador, "productVariantsBulkCreate")
    assert variaveis["strategy"] == "PRESERVE_STANDALONE_VARIANT"
    [criada] = variaveis["variants"]
    assert "id" not in criada
    assert criada["optionValues"] == [{"optionName": "Title", "name": "Prata"}]
    assert criada["inventoryQuantities"] == [
        {"locationId": "gid://shopify/Location/1", "availableQuantity": 4}
    ]
    referencia = ExternalReference.objects.get(object_id=str(nova.pk), entity_type="variantes")
    assert referencia.external_id == "gid://shopify/ProductVariant/2"
    assert referencia.metadata["inventory_item_id"] == "gid://shopify/InventoryItem/2"
    assert ExternalReference.objects.filter(object_id=str(antiga.pk)).exists()
