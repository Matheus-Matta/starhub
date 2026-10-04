"""Consultas GraphQL do produto: em lote (sincronizacao) e um por id (webhook, pedido).

Os dois pedem os mesmos campos (`campos_do_produto`): o que a importacao grava nao
pode depender de o produto ter vindo pela sincronizacao ou pelo webhook.
Doc Admin GraphQL 2026-07: Product.seo e "The SEO title and description that are
associated with a product."; InventoryItem.measurement "The packaging dimensions of
the inventory item.", com `weight` "The weight of the inventory item." (Weight: value
Float + unit WeightUnit). `bodyHtml` e `images` estao deprecados: descriptionHtml e media.

Custo pedido (limite: "A single query may not exceed a cost of 1,000 points"; conexao
custa 2 + `first` x custo do no, objeto 1, escalar 0; conta reproduzida por
tests/custo_graphql.py):
- variante = 1 + inventoryItem 1 + measurement 1 + weight 1 + selectedOptions 1 = 5;
- foto = no 1 + image 1 = 2; cada conexao tem pageInfo 1 (sem ele nao ha como saber
  que a lista veio cortada);
- produto = 1 + seo 1 + options 1 + media (3 + 2f) + collections (3 + c) + variants
  (3 + 5v) = 12 + 2f + c + 5v.
Lote: products(first: 10) = 2 + 10 x produto + pageInfo 1 <= 1000 deixa o produto em
99. Com f = 10, c = 10, v = 10: produto = 92 e lote = 2 + 920 + 1 = 923 (era 3 por
pagina com 936). O que passa de 10 volta inteiro pela consulta por id
(produtos_busca.completar): f = 100, c = 50, v = 100 = 12 + 200 + 50 + 500 = 762.
Foto: o Shopify aceita ate 250 por produto; acima de 100 a consulta por id ainda corta.
"""


# Fotos do produto: video e modelo 3D nao tem `image` e ficam de fora na importacao.
def midias_do_produto(fotos):
    return (f"media(first: {fotos}) {{ nodes {{ id alt ... on MediaImage "
            "{ status image { url altText } } } pageInfo { hasNextPage } }")


def campos_do_produto(colecoes, variantes, fotos):
    return f"""
    id title handle status descriptionHtml vendor productType tags publishedAt
    seo {{ title description }}
    options {{ name position }}
    {midias_do_produto(fotos)}
    collections(first: {colecoes}) {{ nodes {{ id }} pageInfo {{ hasNextPage }} }}
    variants(first: {variantes}) {{ nodes {{ id title sku barcode price compareAtPrice
      inventoryQuantity inventoryPolicy taxable position
      inventoryItem {{ tracked requiresShipping measurement {{ weight {{ value unit }} }} }}
      selectedOptions {{ name value }} }} pageInfo {{ hasNextPage }} }}
    """


# Pagina de 10 com listas curtas: o produto que passa delas e a minoria e paga uma
# consulta a mais; com listas longas a pagina ficava em 3 e todo produto pagava.
CONSULTA_PRODUTOS_LOTE = f"""
  query($cursor: String) {{ products(first: 10, after: $cursor) {{
    nodes {{ {campos_do_produto(10, 10, 10)} }}
    pageInfo {{ hasNextPage endCursor }}
  }} }}
"""

CONSULTA_PRODUTO = f"""
  query($id: ID!) {{ product(id: $id) {{ {campos_do_produto(50, 100, 100)} }} }}
"""
