from apps.shopify.consultas_cupons import CONSULTA_CUPONS
from apps.shopify.consultas_produtos import CONSULTA_PRODUTOS_LOTE

CONSULTAS = {
    # Campos, tamanho da pagina e calculo de custo em consultas_produtos.py. `media` e
    # nao `images` (deprecado na 2026-07): o id e o da MediaImage, o mesmo do envio e
    # do webhook, e a importacao casa a foto pelo vinculo (imagens.py).
    "produtos": ("products", CONSULTA_PRODUTOS_LOTE),
    "categorias": ("collections", """
      query($cursor: String) { collections(first: 50, after: $cursor) {
        nodes { id title handle descriptionHtml image { url altText } }
        pageInfo { hasNextPage endCursor }
      } }
    """),
    # email, phone, emailMarketingConsent e addresses estao deprecados no Customer da
    # 2026-07: vem de defaultEmailAddress, defaultPhoneNumber e addressesV2. Pagina de
    # 25 com 10 enderecos cada fica perto de 400 pontos (limite 1000). Cliente com mais
    # de 10 enderecos traz so os 10 primeiros (hasNextPage avisa).
    "clientes": ("customers", """
      fragment EnderecoCliente on MailingAddress { id firstName lastName company address1
        address2 city province provinceCode zip country countryCodeV2 phone }
      query($cursor: String) { customers(first: 25, after: $cursor) {
        nodes { id firstName lastName note locale state taxExempt createdAt tags
          numberOfOrders amountSpent { amount currencyCode }
          defaultEmailAddress { emailAddress marketingState }
          defaultPhoneNumber { phoneNumber }
          defaultAddress { ...EnderecoCliente }
          addressesV2(first: 10) { nodes { ...EnderecoCliente } pageInfo { hasNextPage } } }
        pageInfo { hasNextPage endCursor }
      } }
    """),
    # Pagina pequena de proposito: o Shopify recusa consulta com custo pedido acima
    # de 1000 pontos, e cada pedido com 50 itens (variante, produto, descontos) ja
    # custa ~300. orders(first: 50) estouraria o limite e a sincronizacao inteira cairia.
    "pedidos": ("orders", """
      fragment Dinheiro on MoneyBag { shopMoney { amount currencyCode } }
      fragment Endereco on MailingAddress { firstName lastName address1 address2 city
        province provinceCode zip country countryCodeV2 phone company }
      fragment Alocacao on DiscountAllocation {
        allocatedAmountSet { ...Dinheiro } discountApplication { index } }
      query($cursor: String) { orders(first: 3, after: $cursor) {
        nodes { id legacyResourceId name email phone createdAt updatedAt processedAt
          cancelledAt cancelReason note customAttributes { key value }
          displayFinancialStatus displayFulfillmentStatus paymentGatewayNames currencyCode
          totalPriceSet { ...Dinheiro } subtotalPriceSet { ...Dinheiro }
          totalDiscountsSet { ...Dinheiro } totalShippingPriceSet { ...Dinheiro }
          customer { id legacyResourceId email firstName lastName phone }
          billingAddress { ...Endereco } shippingAddress { ...Endereco }
          lineItems(first: 50) { nodes { id title name variantTitle sku quantity
            originalUnitPriceSet { ...Dinheiro } totalDiscountSet { ...Dinheiro }
            discountAllocations { ...Alocacao } customAttributes { key value }
            variant { id legacyResourceId sku } product { id legacyResourceId } } }
          shippingLines(first: 5) { nodes { id code title source
            originalPriceSet { ...Dinheiro } discountedPriceSet { ...Dinheiro }
            discountAllocations { ...Alocacao } } }
          discountCodes
          discountApplications(first: 10) { nodes { __typename index targetType
            allocationMethod
            value { __typename ... on MoneyV2 { amount currencyCode }
              ... on PricingPercentageValue { percentage } }
            ... on DiscountCodeApplication { code } } }
          transactions(first: 10) { id kind status gateway processedAt createdAt
            amountSet { ...Dinheiro } } }
        pageInfo { hasNextPage endCursor }
      } }
    """),
    "cupons": ("codeDiscountNodes", CONSULTA_CUPONS),
    "estoque": ("productVariants", """
      query($cursor: String) { productVariants(first: 50, after: $cursor) {
        nodes { id sku inventoryQuantity product { id } }
        pageInfo { hasNextPage endCursor }
      } }
    """),
}

TOPICOS = {
    "produtos": {"create": "PRODUCTS_CREATE", "update": "PRODUCTS_UPDATE",
                 "delete": "PRODUCTS_DELETE"},
    "categorias": {"create": "COLLECTIONS_CREATE", "update": "COLLECTIONS_UPDATE",
                   "delete": "COLLECTIONS_DELETE"},
    "clientes": {"create": "CUSTOMERS_CREATE", "update": "CUSTOMERS_UPDATE",
                 "delete": "CUSTOMERS_DELETE"},
    "pedidos": {"create": "ORDERS_CREATE", "update": "ORDERS_UPDATED",
                "delete": "ORDERS_DELETE"},
    "cupons": {"create": "DISCOUNTS_CREATE", "update": "DISCOUNTS_UPDATE",
               "delete": "DISCOUNTS_DELETE"},
    "estoque": {"update": "INVENTORY_LEVELS_UPDATE"},
}

MUTATION_WEBHOOK = """
mutation CriarWebhook($topic: WebhookSubscriptionTopic!, $webhook: WebhookSubscriptionInput!) {
  webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhook) {
    webhookSubscription { id topic uri }
    userErrors { field message }
  }
}
"""

CONSULTA_WEBHOOKS = """
query ListarWebhooks($cursor: String) {
  webhookSubscriptions(first: 100, after: $cursor) {
    nodes { id topic uri }
    pageInfo { hasNextPage endCursor }
  }
}
"""

MUTATION_EXCLUIR_WEBHOOK = """
mutation ExcluirWebhook($id: ID!) {
  webhookSubscriptionDelete(id: $id) {
    deletedWebhookSubscriptionId
    userErrors { field message }
  }
}
"""

# Contagem de cada raiz das CONSULTAS para a barra de progresso da sincronizacao.
# Cupons (codeDiscountNodes) ficam de fora: o discountNodesCount conta tambem os
# descontos automaticos, e o total nao bateria com o que a busca traz.
CONTAGENS = {
    "products": "productsCount",
    "collections": "collectionsCount",
    "customers": "customersCount",
    "orders": "ordersCount",
    "productVariants": "productVariantsCount",
}
