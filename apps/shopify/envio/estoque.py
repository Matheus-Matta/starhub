"""Estoque da variante do hub -> quantidade "available" no local principal do Shopify.

O hub manda o numero absoluto (inventorySetQuantities) e nao um delta: se um envio
se perder ou repetir, o proximo deixa a loja igual ao hub de novo.
"""

import uuid

from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.loja.models import VarianteProduto
from apps.shopify.cliente import ShopifyErro
from apps.shopify.envio.base import VARIANTES, RecursoShopify

# Desde a 2026-04 o Shopify exige @idempotent nesta mutation.
DEFINIR = """mutation($input: InventorySetQuantitiesInput!, $idempotencyKey: String!) {
  inventorySetQuantities(input: $input) @idempotent(key: $idempotencyKey) {
    inventoryAdjustmentGroup { reason }
    userErrors { code field message }
  }
}"""
ITEM_DA_VARIANTE = """query($id: ID!) {
  productVariant(id: $id) { inventoryItem { id } }
}"""


class EstoqueShopify(RecursoShopify):
    recurso = "estoque"
    # O vinculo e o da variante: estoque nao tem id proprio no Shopify.
    entidade = VARIANTES
    modelo = VarianteProduto

    def criar(self, obj):
        raise EnvioNaoSuportado(
            "estoque so e enviado para variante ja vinculada; o produto cria a variante."
        )

    def excluir(self, external_id):
        raise EnvioNaoSuportado("estoque nao se exclui; a variante sai junto com o produto.")

    def atualizar(self, obj, external_id):
        if not obj.manage_inventory:
            raise EnvioNaoSuportado(
                f"variante {obj.pk} esta sem controle de estoque no hub; nada a enviar."
            )
        variante_gid = self.gid("ProductVariant", external_id)
        entrada = {
            "name": "available",
            "reason": "correction",
            "referenceDocumentUri": f"gid://starhub/VarianteProduto/{obj.pk}",
            "quantities": [{
                "inventoryItemId": self._item(obj, variante_gid),
                "locationId": self.local_principal(),
                "quantity": obj.inventory_quantity,
                # null desliga o compare-and-swap: o hub e a fonte do estoque e o
                # valor absoluto dele vale mesmo que a loja tenha mudado no meio.
                "changeFromQuantity": None,
            }],
        }
        # Chave nova por envio: a mesma chave com outra quantidade faria o Shopify
        # devolver a resposta guardada e ignorar a quantidade nova.
        self.mutacao(DEFINIR, {"input": entrada, "idempotencyKey": str(uuid.uuid4())},
                     "inventorySetQuantities")

    def _item(self, variante, variante_gid):
        referencia = self.referencias_variantes().filter(object_id=str(variante.pk)).first()
        item = ((referencia.metadata or {}).get("inventory_item_id")) if referencia else None
        if item:
            return item
        dados = self.cliente.graphql(ITEM_DA_VARIANTE, {"id": variante_gid}) or {}
        item = ((dados.get("productVariant") or {}).get("inventoryItem") or {}).get("id")
        if not item:
            raise ShopifyErro(
                f"A variante {variante_gid} nao existe mais na loja; sincronize os produtos "
                "para refazer o vinculo."
            )
        if referencia:
            # Guardado para o proximo envio nao consultar de novo.
            referencia.metadata = {**(referencia.metadata or {}), "inventory_item_id": item}
            referencia.save(update_fields=["metadata", "updated_at"])
        return item
