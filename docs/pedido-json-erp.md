# JSON do pedido na API Woo do StarHub

Este documento explica, campo por campo, o JSON que o StarHub devolve para um
pedido na API compatível com o WooCommerce. O foco é **o que o ERP recebe**,
inclusive os campos próprios do StarHub: serviços do item, agendamento da entrega
e id do vendedor.

## Como pedir

```http
GET /wp-json/wc/v3/orders/<id>        um pedido
GET /wp-json/wc/v3/orders             lista (mesmo formato, um por posição)
Authorization: Basic base64(ck_...:cs_...)
```

A lista aceita `status`, `customer`, `product`, `parent`, `modified_after`,
`modified_before`, `page` e `per_page`. O total de pedidos vem no cabeçalho
`X-WP-Total`, e o número de páginas, em `X-WP-TotalPages`.

Regras de formato, iguais às do WooCommerce:

- **Dinheiro** vem como texto com ponto e 2 casas: `"1479.81"`. A única exceção é
  o `price` do item, que é número (`1349.91`), como no Woo.
- **Datas** vêm sem fuso, no horário da loja (`"2026-09-30T10:00:00"`). O par
  `_gmt` traz a mesma data em UTC (`"2026-09-30T13:00:00"`). Data que não
  aconteceu vem `null`.
- **meta_data** é uma lista de `{"id", "key", "value"}`. O `id` só numera os
  itens dentro da própria lista.

## Exemplo completo

Pedido feito na loja Shopify: uma poltrona com impermeabilização e montagem,
duas almofadas, cupom de 10%, frete e entrega agendada. A integração Shopify
tem o vendedor 12 configurado. Este JSON é conferido pelos testes contra o que a
API devolve de verdade. Só os ids do banco, a chave do pedido e a data de
alteração foram fixados.

<!-- pedido-completo:inicio -->
```json
{
  "id": 1,
  "parent_id": 0,
  "status": "processing",
  "currency": "BRL",
  "version": "9.0.0",
  "prices_include_tax": false,
  "date_created": "2026-09-30T10:00:00",
  "date_created_gmt": "2026-09-30T13:00:00",
  "date_modified": "2026-09-30T15:00:05",
  "date_modified_gmt": "2026-09-30T18:00:05",
  "discount_total": "159.99",
  "discount_tax": "0.00",
  "shipping_total": "39.90",
  "shipping_tax": "0.00",
  "cart_tax": "0.00",
  "total": "1479.81",
  "total_tax": "0.00",
  "customer_id": 1,
  "order_key": "wc_order_a1b2c3d4e5f60",
  "billing": {
    "first_name": "Maria",
    "last_name": "Silva",
    "company": "",
    "address_1": "Rua das Flores",
    "address_2": "Apto 10, Centro",
    "city": "São Paulo",
    "state": "SP",
    "postcode": "01000-000",
    "country": "BR",
    "email": "maria@example.com",
    "phone": "+5511999999999",
    "number": "100",
    "neighborhood": "Centro",
    "cpf": "12345678900",
    "persontype": "1"
  },
  "shipping": {
    "first_name": "Maria",
    "last_name": "Silva",
    "company": "",
    "address_1": "Rua das Flores",
    "address_2": "Apto 10, Centro",
    "city": "São Paulo",
    "state": "SP",
    "postcode": "01000-000",
    "country": "BR",
    "phone": "",
    "number": "100",
    "neighborhood": "Centro"
  },
  "payment_method": "pix",
  "payment_method_title": "appmax_pix",
  "transaction_id": "123456789",
  "customer_ip_address": "",
  "customer_user_agent": "",
  "created_via": "shopify",
  "customer_note": "Observação do pedido",
  "date_completed": null,
  "date_completed_gmt": null,
  "date_paid": "2026-09-30T10:00:00",
  "date_paid_gmt": "2026-09-30T13:00:00",
  "cart_hash": "",
  "number": "1",
  "meta_data": [
    {
      "id": 1,
      "key": "starhub",
      "value": {
        "origem": {
          "canal": "shopify",
          "id": "123456789",
          "numero": "1001",
          "nome": "#1001",
          "url": "https://loja.myshopify.com/admin/orders/123456789",
          "status_financeiro": "paid",
          "atualizado_em": "2026-09-30T15:00:00-03:00"
        },
        "cliente": {
          "cpf": "12345678900",
          "tipo_pessoa": "1"
        },
        "entrega": {
          "agendamento": "15-10-2026",
          "tipo": "delivery"
        },
        "cupons": [
          "PROMO10"
        ],
        "idVendedor": 12
      }
    }
  ],
  "line_items": [
    {
      "id": 1,
      "name": "Poltrona Exemplo",
      "product_id": 1,
      "variation_id": 0,
      "quantity": 1,
      "tax_class": "",
      "subtotal": "1499.90",
      "subtotal_tax": "0.00",
      "total": "1349.91",
      "total_tax": "0.00",
      "taxes": [],
      "meta_data": [
        {
          "id": 1,
          "key": "starhub",
          "value": {
            "servicos": [
              {
                "id": 1,
                "nome": "Impermeabilização da poltrona",
                "sku": "SERV-IMPERMEABILIZACAO-DA-POLTRONA",
                "preco": "499.99",
                "opcao": "Sim"
              },
              {
                "id": 2,
                "nome": "Montagem",
                "sku": "SERV-MONTAGEM",
                "preco": "120.00",
                "opcao": "Sim"
              }
            ]
          }
        },
        {
          "id": 2,
          "key": "epofw_field_1",
          "value": "{\"epofw_field_1\": {\"epofw_field_quantity\": \"1\", \"epofw_label\": \"IMPERMEABILIZAÇÃO DA POLTRONA:\", \"product_id\": \"1\", \"epofw_type\": \"radiogroup\", \"epofw_name\": \"epofw_field_1\", \"epofw_value\": \"Sim\", \"epofw_price\": \"499.99\", \"epofw_original_price\": \"499.99\", \"epofw_price_type\": \"fixed\", \"epofw_form_data\": {\"field_status\": \"on\", \"field\": {\"type\": \"radiogroup\", \"name\": \"1\", \"id\": \"1\", \"class\": \"1\"}, \"label\": {\"title\": \"IMPERMEABILIZAÇÃO DA POLTRONA:\", \"class\": \"epofw_label_1\", \"subtitle\": \"\", \"subtitle_class\": \"\"}, \"epofw_field_settings\": {\"options\": {\"Sim\": \"Sim||fixed||499,99\", \"Não\": \"Não||fixed||0,00\"}}}}}"
        },
        {
          "id": 3,
          "key": "epofw_field_2",
          "value": "{\"epofw_field_2\": {\"epofw_field_quantity\": \"1\", \"epofw_label\": \"MONTAGEM:\", \"product_id\": \"1\", \"epofw_type\": \"radiogroup\", \"epofw_name\": \"epofw_field_2\", \"epofw_value\": \"Sim\", \"epofw_price\": \"120.00\", \"epofw_original_price\": \"120.00\", \"epofw_price_type\": \"fixed\", \"epofw_form_data\": {\"field_status\": \"on\", \"field\": {\"type\": \"radiogroup\", \"name\": \"2\", \"id\": \"2\", \"class\": \"2\"}, \"label\": {\"title\": \"MONTAGEM:\", \"class\": \"epofw_label_2\", \"subtitle\": \"\", \"subtitle_class\": \"\"}, \"epofw_field_settings\": {\"options\": {\"Sim\": \"Sim||fixed||120,00\", \"Não\": \"Não||fixed||0,00\"}}}}}"
        }
      ],
      "sku": "POLTRONA-001",
      "price": 1349.91,
      "image": {
        "id": "",
        "src": ""
      },
      "parent_name": null
    },
    {
      "id": 2,
      "name": "Almofada Avulsa",
      "product_id": 0,
      "variation_id": 0,
      "quantity": 2,
      "tax_class": "",
      "subtotal": "100.00",
      "subtotal_tax": "0.00",
      "total": "90.00",
      "total_tax": "0.00",
      "taxes": [],
      "meta_data": [],
      "sku": "ALMOFADA-SEM-CADASTRO",
      "price": 45.0,
      "image": {
        "id": "",
        "src": ""
      },
      "parent_name": null
    }
  ],
  "tax_lines": [],
  "shipping_lines": [
    {
      "id": 1,
      "method_id": "standard",
      "method_title": "Entrega padrão",
      "total": "39.90",
      "total_tax": "0.00",
      "taxes": [],
      "meta_data": []
    }
  ],
  "fee_lines": [],
  "coupon_lines": [
    {
      "id": 1,
      "code": "PROMO10",
      "discount": "159.99",
      "discount_tax": "0.00",
      "meta_data": []
    }
  ],
  "refunds": [],
  "payment_url": "",
  "is_editable": false,
  "needs_payment": false,
  "needs_processing": true,
  "currency_symbol": "R$"
}
```
<!-- pedido-completo:fim -->

## Campos do pedido

| Campo | Tipo | O que é |
|---|---|---|
| `id` | número | Id do pedido no StarHub. Use este id nas rotas `/orders/<id>`. |
| `number` | texto | O mesmo `id`, em texto (como o Woo). O número da loja de origem fica em `meta_data` > `starhub.origem.numero`. |
| `parent_id` | número | Pedido pai; `0` quando não há. |
| `status` | texto | `pending` (aguardando pagamento), `processing` (pago, a separar), `on-hold` (aguardando), `completed` (concluído), `cancelled`, `refunded`, `failed`, `trash`, `checkout-draft`. |
| `currency` / `currency_symbol` | texto | Moeda (`BRL`) e símbolo (`R$`). |
| `version` | texto | Versão do formato Woo imitada (`9.0.0`). |
| `prices_include_tax` | booleano | Se os preços já incluem imposto. |
| `date_created` (+`_gmt`) | data | Quando o pedido foi feito **na loja de origem**; pedido criado no próprio StarHub usa a data de criação nele. |
| `date_modified` (+`_gmt`) | data | Última alteração do pedido no StarHub. Use com `modified_after` para buscar só o que mudou. |
| `date_paid` (+`_gmt`) | data ou null | Quando foi pago. |
| `date_completed` (+`_gmt`) | data ou null | Quando foi concluído. |
| `discount_total` | dinheiro | Soma dos descontos (cupons inclusive). |
| `shipping_total` | dinheiro | Frete. |
| `total` | dinheiro | Valor final pago: itens - descontos + frete + impostos. |
| `discount_tax`, `shipping_tax`, `cart_tax`, `total_tax` | dinheiro | Impostos (no Brasil, normalmente `"0.00"`). |
| `customer_id` | número | Id do cliente no StarHub (`/customers/<id>`); `0` para visitante. |
| `order_key` | texto | Chave do pedido no formato do Woo (`wc_order_...`). |
| `billing` | objeto | Endereço de cobrança e contato (ver abaixo). |
| `shipping` | objeto | Endereço de entrega (ver abaixo). |
| `payment_method` / `payment_method_title` | texto | Forma de pagamento (`pix`) e o nome que a loja usa (`appmax_pix`). |
| `transaction_id` | texto | Id da transação. Nos pedidos do Shopify é o id do pedido na Shopify. |
| `created_via` | texto | Origem do pedido: `shopify`, `woocommerce`, `suri`... |
| `customer_note` | texto | Observação que o cliente escreveu. |
| `customer_ip_address`, `customer_user_agent`, `cart_hash`, `payment_url` | texto | Campos do Woo; vazios quando a origem não informa. |
| `is_editable`, `needs_payment`, `needs_processing` | booleano | Mesma regra do Woo, pelo `status`. |
| `meta_data` | lista | Dados do StarHub no nível do pedido (ver "meta_data do pedido"). |
| `line_items` | lista | Itens (ver "Itens"). |
| `shipping_lines` | lista | Fretes: `method_id`, `method_title`, `total`. |
| `coupon_lines` | lista | Cupons: `code` (o código que o cliente digitou) e `discount` (quanto ele descontou). |
| `fee_lines`, `tax_lines`, `refunds` | lista | Taxas, impostos e reembolsos; vazios quando não há. |

### billing e shipping

Os campos do Woo (`first_name`, `last_name`, `company`, `address_1`, `address_2`,
`city`, `state`, `postcode`, `country`, `phone`) mais os campos brasileiros:

| Campo | Onde | O que é |
|---|---|---|
| `address_1` | os dois | Só a rua, sem o número. |
| `number` | os dois | Número do endereço. |
| `neighborhood` | os dois | Bairro. |
| `email` | só `billing` | E-mail do cliente. |
| `cpf` | só `billing` | CPF ou CNPJ, só dígitos. |
| `persontype` | só `billing` | `"1"` pessoa física (CPF), `"2"` pessoa jurídica (CNPJ). |

## meta_data do pedido

Tudo o que é do StarHub vem em **um item só**, com `"key": "starhub"`. O `value`
é um objeto com seções:

```json
{"key": "starhub", "value": {
  "origem":  {"canal": "shopify", "id": "123456789", "numero": "1001", "nome": "#1001",
              "url": "https://loja.myshopify.com/admin/orders/123456789",
              "status_financeiro": "paid", "atualizado_em": "2026-09-30T15:00:00-03:00"},
  "cliente": {"cpf": "12345678900", "tipo_pessoa": "1"},
  "entrega": {"agendamento": "15-10-2026", "tipo": "delivery"},
  "cupons":  ["PROMO10"],
  "idVendedor": 12
}}
```

| Campo | Tipo | O que é |
|---|---|---|
| `origem.canal` | texto | Loja de onde o pedido veio. |
| `origem.id` | texto | Id do pedido na loja de origem. |
| `origem.numero` / `origem.nome` | texto | Número do pedido na loja (`1001`) e como ela o mostra (`#1001`). |
| `origem.url` | texto | Link do pedido no painel da loja. |
| `origem.status_financeiro` | texto | Situação do pagamento na loja (`paid`, `pending`, `refunded`...). |
| `origem.atualizado_em` | texto | Última alteração na loja, com fuso. |
| `cliente.cpf` / `cliente.tipo_pessoa` | texto | Mesmo CPF/CNPJ e tipo de pessoa do `billing`. |
| `entrega.agendamento` | texto | **Data agendada para a entrega, sempre `dd-mm-aaaa`** (`"15-10-2026"`), seja qual for o formato em que a loja mandou. Se o cliente escreveu algo que não é data (ex.: `"a combinar"`), vem o texto como ele escreveu. |
| `entrega.tipo` | texto | `delivery` (entrega) ou `pickup` (retirada na loja). |
| `cupons` | lista de texto | Códigos de cupom usados (os mesmos de `coupon_lines`). |
| `idVendedor` | número inteiro | **Id do vendedor no ERP** para este pedido. Cada loja de origem tem o seu: é o número configurado na integração da loja no StarHub. |

Seção sem dado não aparece. Se o pedido não tem nenhum dado do StarHub, o item
`starhub` não vem.

Hoje, **serviços e agendamento só existem em pedidos do Shopify**. O `idVendedor`
só vem quando a integração da loja de origem tem o número configurado. Pedido de
outra origem, ou de loja sem o número, vem sem esses campos, e não com zero ou
vazio.

## Itens (line_items)

| Campo | Tipo | O que é |
|---|---|---|
| `id` | número | Id da linha. Use-o para alterar a linha num PUT. |
| `name` / `sku` | texto | Nome e SKU do produto como foi vendido. |
| `product_id` | número | Id do produto no StarHub (`/products/<id>`); `0` se o produto não está cadastrado. |
| `variation_id` | número | Id da variação; `0` sem variação. |
| `quantity` | número | Quantidade. |
| `subtotal` | dinheiro | Preço × quantidade, antes do desconto. |
| `total` | dinheiro | Valor da linha depois do desconto. |
| `price` | número | `total / quantity`. |
| `subtotal_tax`, `total_tax`, `taxes`, `tax_class` | | Impostos da linha. |
| `image` | objeto | `{"id", "src"}` da primeira foto do produto. |
| `meta_data` | lista | Serviços contratados para este item (abaixo). Item sem serviço vem com a lista vazia. |

### Serviços do item

Serviço extra (montagem, impermeabilização, garantia estendida) é do item que o
cliente comprou. Por isso ele vem no `meta_data` **do item**, com a mesma chave
`starhub`:

```json
{"key": "starhub", "value": {"servicos": [
  {"id": 1, "nome": "Impermeabilização da poltrona",
   "sku": "SERV-IMPERMEABILIZACAO-DA-POLTRONA", "preco": "499.99", "opcao": "Sim"},
  {"id": 2, "nome": "Montagem", "sku": "SERV-MONTAGEM", "preco": "120.00", "opcao": "Sim"}
]}}
```

| Campo | Tipo | O que é |
|---|---|---|
| `id` | número | Id do serviço no cadastro de Serviços do StarHub. Não muda. |
| `nome` | texto | Nome do serviço. |
| `sku` | texto | SKU do serviço. Serviço que chega pela primeira vez é cadastrado na hora com `SERV-<NOME>`; a loja pode trocar pelo código do ERP no cadastro, e a troca vale para todos os pedidos. |
| `preco` | dinheiro | Quanto o cliente pagou pelo serviço **neste item**. |
| `opcao` | texto | O que o cliente escolheu (`"Sim"`, `"12 meses"`...). |

Só vem serviço contratado. Quando o cliente escolhe "Não", o serviço não aparece.

Ao lado, o mesmo serviço vem no formato do plugin **EPOFW** (`epofw_field_1`,
`epofw_field_2`...), para quem já lê serviços como numa loja Woo com esse plugin.
O `value` desse item é **um texto com JSON dentro** (como o Woo grava), e não um
objeto. O `epofw_label` é o nome em maiúsculas com dois-pontos
(`"MONTAGEM:"`), e `epofw_price` é o preço. Use um dos dois formatos, não
some os dois: são o mesmo serviço.

## Devolvendo o pedido (PUT)

O ERP pode mandar de volta o pedido como recebeu (`PUT /wp-json/wc/v3/orders/<id>`)
sem duplicar nada:

- os serviços do `starhub` do item trocam os serviços daquele item. `id` e `sku`
  vêm do cadastro e são ignorados na entrada. `"servicos": []` tira os serviços
  do item;
- `idVendedor` é ignorado na entrada, porque vem sempre da configuração da
  integração;
- `entrega.agendamento` pode voltar em `dd-mm-aaaa`.
