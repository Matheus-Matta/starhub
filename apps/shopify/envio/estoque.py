"""Estoque da variante do hub -> quantidade "available" no local principal do Shopify.

O hub manda o numero absoluto (inventorySetQuantities) e nao um delta: se um envio
se perder ou repetir, o proximo deixa a loja igual ao hub de novo.

A variante da loja e a do vinculo; se ela nao existe mais (recriada la, ou o produto
religado), vale o SKU: a variante da loja com o mesmo SKU recebe o estoque e o vinculo.
Sem isso a baixa/entrada falhava ate alguem sincronizar o produto.
"""

import uuid

from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.loja.models import VarianteProduto
from apps.shopify.cliente import ShopifyErro
from apps.shopify.envio import produtos_variantes as variantes_shopify
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
# "first: 2": dois resultados = SKU repetido na loja, e ai nao da para escolher.
PELO_SKU = """query($q: String!) {
  productVariants(first: 2, query: $q) {
    nodes { id product { id } inventoryItem { id } }
  }
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
        try:
            self._definir(obj, self._item(obj, variante_gid))
        except ShopifyErro as erro:
            # inventoryItem guardado pode ser de uma variante apagada na loja: confere
            # de novo (pelo id, depois pelo SKU) e tenta uma vez. Se o item e o mesmo, o
            # erro e outro (ex.: nao estocado no local) e volta como veio.
            velho = self._esquecer_item(obj)
            if not velho:
                raise
            try:
                novo = self._item(obj, variante_gid)
            except ShopifyErro:
                raise erro from None
            if novo == velho:
                raise
            self._definir(obj, novo)

    def _definir(self, obj, item):
        entrada = {
            "name": "available",
            "reason": "correction",
            "referenceDocumentUri": f"gid://starhub/VarianteProduto/{obj.pk}",
            "quantities": [{
                "inventoryItemId": item,
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
            return self._pelo_sku(variante, referencia, variante_gid)
        if referencia:
            # Guardado para o proximo envio nao consultar de novo.
            referencia.metadata = {**(referencia.metadata or {}), "inventory_item_id": item}
            referencia.save(update_fields=["metadata", "updated_at"])
        return item

    def _esquecer_item(self, variante):
        """Apaga o inventoryItem guardado no vinculo e devolve qual era ("" se nenhum)."""
        referencia = self.referencias_variantes().filter(object_id=str(variante.pk)).first()
        velho = ((referencia.metadata or {}).get("inventory_item_id")) if referencia else ""
        if velho:
            referencia.metadata = {k: v for k, v in referencia.metadata.items()
                                   if k != "inventory_item_id"}
            referencia.save(update_fields=["metadata", "updated_at"])
        return velho or ""

    def _pelo_sku(self, variante, referencia, variante_gid):
        sku = (variante.sku or "").strip().replace('"', "")
        dados = (self.cliente.graphql(PELO_SKU, {"q": f'sku:"{sku}"'}) or {}) if sku else {}
        achadas = ((dados.get("productVariants") or {}).get("nodes")) or []
        if len(achadas) != 1:
            motivo = "SKU repetido na loja" if achadas else "nenhuma variante com o SKU"
            raise ShopifyErro(
                f"A variante {variante_gid} nao existe mais na loja e {motivo} "
                f"({sku or 'sem SKU'}); sincronize o produto para refazer o vinculo.")
        pai = (achadas[0].get("product") or {}).get("id") or (
            referencia.external_parent_id if referencia else "")
        variantes_shopify.vincular(self, variante, achadas[0], pai)
        return achadas[0]["inventoryItem"]["id"]
