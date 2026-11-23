"""Variante nova na loja: no productSet do create e em lote no update (produtos.py)."""

from apps.shopify.envio import produtos_variantes as variantes_shopify

CRIAR = """mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!,
    $strategy: ProductVariantsBulkCreateStrategy) {
  productVariantsBulkCreate(productId: $productId, variants: $variants, strategy: $strategy) {
    productVariants { id inventoryItem { id } } userErrors { field message }
  }
}"""


def estoque_inicial(enviador, variante, formato):
    # So na criacao da variante: depois o estoque segue pelo recurso "estoque",
    # que tem o seu proprio liga/desliga na configuracao.
    if not variante.manage_inventory:
        return None
    if formato == "set":
        return [{"locationId": enviador.local_principal(), "name": "available",
                 "quantity": variante.inventory_quantity}]
    return [{"locationId": enviador.local_principal(),
             "availableQuantity": variante.inventory_quantity}]


def no_set(enviador, variante, posicao, opcoes):
    # ProductVariantSetInput tem `sku` no topo (o lote nao tem).
    dados = {**variantes_shopify.comum(variante), "position": posicao, "sku": variante.sku,
             "optionValues": variantes_shopify.valores_de_opcao(opcoes)}
    estoque = estoque_inicial(enviador, variante, "set")
    if estoque:
        dados["inventoryQuantities"] = estoque
    return dados


def criar(enviador, produto_gid, novas, varias):
    entrada = []
    for variante in novas:
        opcoes = variantes_shopify.opcoes_da_variante(variante, varias)
        dados = {**variantes_shopify.em_lote(variante),
                 "optionValues": variantes_shopify.valores_de_opcao(opcoes)}
        estoque = estoque_inicial(enviador, variante, "lote")
        if estoque:
            dados["inventoryQuantities"] = estoque
        entrada.append(dados)
    # PRESERVE: o DEFAULT apaga a variante "Default Title" da loja, e o update nunca
    # apaga variante.
    criadas = enviador.mutacao(CRIAR, {
        "productId": produto_gid, "variants": entrada,
        "strategy": "PRESERVE_STANDALONE_VARIANT",
    }, "productVariantsBulkCreate").get("productVariants") or []
    # O Shopify devolve as criadas na ordem da entrada.
    for variante, recebida in zip(novas, criadas, strict=False):
        variantes_shopify.vincular(enviador, variante, recebida, produto_gid)
