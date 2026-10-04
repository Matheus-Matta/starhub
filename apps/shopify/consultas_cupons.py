"""Consultas GraphQL de desconto por codigo (DiscountCodeNode), API 2026-07.

Um fragmento so para a sincronizacao, o webhook e o pedido: os tres caminhos
leem os mesmos campos e cadastram o cupom igual (apps/shopify/cupons_mapa.py).

Custo: o Shopify recusa consulta acima de 1000 pontos. Cada desconto com
produtos, variantes e colecoes ($itens por lista) custa ~120 com $itens = 50,
por isso a pagina da sincronizacao e de 5 descontos (~600). Lista que passar de
$itens fica marcada em o metadata do vinculo do cupom (listas_incompletas).
"""

_COMUNS = """title status startsAt endsAt usageLimit appliesOncePerCustomer asyncUsageCount
      codes(first: 5) { nodes { code } }
      combinesWith { orderDiscounts productDiscounts shippingDiscounts }
      context { ...Contexto }"""

FRAGMENTOS = """
  fragment Contexto on DiscountContext { __typename
    ... on DiscountCustomers { customers { id } }
    ... on DiscountCustomerSegments { segments { id name } } }
  fragment Minimo on DiscountMinimumRequirement { __typename
    ... on DiscountMinimumQuantity { greaterThanOrEqualToQuantity }
    ... on DiscountMinimumSubtotal { greaterThanOrEqualToSubtotal { amount currencyCode } } }
  fragment Itens on DiscountItems { __typename
    ... on DiscountProducts {
      products(first: $itens) { nodes { id } pageInfo { hasNextPage } }
      productVariants(first: $itens) { nodes { id sku } pageInfo { hasNextPage } } }
    ... on DiscountCollections {
      collections(first: $itens) { nodes { id } pageInfo { hasNextPage } } } }
  fragment Desconto on DiscountCodeNode { id codeDiscount { __typename
    ... on DiscountCodeBasic { COMUNS summary minimumRequirement { ...Minimo }
      customerGets { items { ...Itens } value { __typename
        ... on DiscountPercentage { percentage }
        ... on DiscountAmount { appliesOnEachItem amount { amount currencyCode } } } } }
    ... on DiscountCodeFreeShipping { COMUNS summary minimumRequirement { ...Minimo }
      maximumShippingPrice { amount currencyCode } }
    ... on DiscountCodeBxgy { COMUNS summary }
    ... on DiscountCodeApp { COMUNS } } }
""".replace("COMUNS", _COMUNS)

CONSULTA_CUPONS = FRAGMENTOS + """
  query($cursor: String, $itens: Int = 50) {
    codeDiscountNodes(first: 5, after: $cursor) {
      nodes { ...Desconto }
      pageInfo { hasNextPage endCursor }
    } }
"""

# Um desconto so: cabe listar ate 100 itens de cada lista (~250 pontos).
CONSULTA_CUPOM_POR_CODIGO = FRAGMENTOS + """
  query($code: String!, $itens: Int = 100) {
    codeDiscountNodeByCode(code: $code) { ...Desconto } }
"""

CONSULTA_CUPOM_POR_ID = FRAGMENTOS + """
  query($id: ID!, $itens: Int = 100) { codeDiscountNode(id: $id) { ...Desconto } }
"""
