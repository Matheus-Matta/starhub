# API de Pedidos para o ERP

A API StarHub fornece as mesmas rotas que o WooCommerce para que o ERP integre como se estivesse conectado a uma loja Woo real.

## De onde vem o pedido

Hoje so o Shopify manda pedidos (webhook `orders/create` e `orders/updated`, mais a sincronizacao GraphQL, em `apps/shopify`). O processo:

1. **Webhook**: marketplace envia o pedido para StarHub
2. **Sincronizacao**: StarHub importa o pedido e seus itens
3. **Produto faltante**: se algum item refencia um produto que nao existe, o importador tenta buscar e importar do Shopify (via `garantir_produto`)
4. **Cupom**: o cupom e identificado pelo **nome**, unico por conta. O codigo interno e aleatorio (12 caracteres) e nao aparece no admin. Quando o pedido traz um codigo que o hub nao conhece:
   - o hub consulta o desconto no Shopify (`codeDiscountNodeByCode`) e cria o cupom completo: tipo, valor, datas, limites de uso, minimo e clientes, produtos e categorias elegiveis. O nome do cupom e o **titulo do desconto**;
   - o segundo pedido com o mesmo codigo nao consulta o Shopify de novo;
   - se o Shopify nao conhece o codigo, o cupom nasce **ativo** com nome igual ao codigo e com tipo e valor que o pedido informa;
   - se a API do Shopify der erro, a importacao do pedido e desfeita e ele pode ser reprocessado depois;
   - nas `coupon_lines` do pedido, o `code` continua sendo o codigo que o cliente digitou.

   Exemplo: chega um pedido com o codigo `PROMO10`. No Shopify o desconto se chama "Black Friday 10%". No hub fica o cupom "Black Friday 10%" (10% de desconto, com as regras do Shopify), e a `coupon_line` do pedido segue com `"code": "PROMO10"`.

   Ja o cupom que o ERP manda em `coupon_lines` num PUT, com codigo desconhecido, e criado pelo nome igual ao codigo, em **rascunho** (valor fixo, para alguem conferir)

## Rotas da API v3

Todas devolvem JSON no formato WooCommerce. Barra final e opcional.

### GET /wp-json/wc/v3/orders

Lista pedidos com filtros:

- `status`: um ou mais status separados por virgula (ex.: `pending,processing,completed`)
- `customer`: id do cliente
- `product`: id do produto (pedidos que contem este item)
- `parent`: ids do pedido pai (`parent_id`)
- `modified_after` e `modified_before`: data de alteracao no formato ISO 8601 sem fuso (ex.: `2026-09-30T12:00:00`)
- `page` e `per_page`: paginacao (padrao: page 1, per_page 10)

Resposta inclui cabecalhos:
- `X-WP-Total`: total de registros
- `X-WP-TotalPages`: numero de paginas

Exemplo:

```bash
curl -u chave:segredo \
  "https://seu-hub/wp-json/wc/v3/orders?status=processing&page=1&per_page=10&modified_after=2026-09-30T12:00:00"
```

### GET /wp-json/wc/v3/orders/<id>

Retorna um pedido completo com todos os campos.

```bash
curl -u chave:segredo "https://seu-hub/wp-json/wc/v3/orders/1"
```

### PUT /wp-json/wc/v3/orders/<id>

Atualiza campos do pedido (status, endereco, itens, metadados, etc).

```bash
curl -X PUT -u chave:segredo \
  -H "Content-Type: application/json" \
  -d '{"status": "completed"}' \
  "https://seu-hub/wp-json/wc/v3/orders/1"
```

### PATCH /wp-json/wc/v3/orders/<id>

Mesmo que PUT (atualiza parcial).

### DELETE /wp-json/wc/v3/orders/<id>

Nao permitido: recusa com 404 rest_no_route. Para tirar um pedido de circulacao, atualize o status para `trash` (existe em `Pedido.Status`).

### POST /wp-json/wc/v3/orders

Nao permitido. Pedidos novo vem do marketplace. Tentar criar recusa com 404 rest_no_route.

### POST /wp-json/wc/v3/orders/batch

Atualiza multiplos pedidos de uma vez. As secoes "create" e "delete" com itens sao recusadas (404 rest_no_route). Lista vazia e aceita, mas nao precisa enviar.

Exemplo:

```json
{
  "update": [
    {"id": 1, "status": "completed"},
    {"id": 2, "status": "processing"}
  ]
}
```

## Campo starhub nos metadados

Todos os dados especificos do StarHub ficam em um unico campo `meta_data` com chave "starhub". Seu value e um objeto JSON com subsecoes:

### Origem do pedido

De onde veio o pedido (marketplace, numero, data de atualizacao, status de pagamento).

```json
"origem": {
  "canal": "shopify",
  "id": "123456789",
  "numero": "1001",
  "nome": "#1001",
  "url": "https://loja.shopify.com/admin/orders/123456789",
  "status_financeiro": "paid",
  "atualizado_em": "2026-09-30T15:00:00-03:00"
}
```

### Cliente

CPF e tipo de pessoa.

```json
"cliente": {
  "cpf": "12345678900",
  "tipo_pessoa": "1"
}
```

### Entrega

Data agendada e tipo (delivery, pickup, etc). O agendamento sai sempre em
`dd-mm-aaaa`, seja qual for o formato que a loja mandou; texto que nao e data sai
como veio.

```json
"entrega": {
  "agendamento": "15-10-2026",
  "tipo": "delivery"
}
```

### Vendedor

`idVendedor` (numero inteiro): o id do vendedor no ERP configurado na integracao
da loja de origem (Integracoes > loja > "ID do vendedor no ERP"). Sem numero
configurado, o campo nao sai. No PUT ele e ignorado.

```json
"idVendedor": 12
```

### Cupons

Lista de codigos de cupom aplicados ao pedido.

```json
"cupons": ["PROMO10"]
```

### Servicos (no item, nao no pedido)

Servico extra (montagem, impermeabilizacao, garantia) e do item: sai no `meta_data` do proprio `line_item`, com a mesma chave `starhub`. Cada servico traz `id` e `sku` do **cadastro de Servicos** do hub (Loja > Servicos), `nome`, `preco` pago neste item e `opcao`. Servico que chega num pedido sem cadastro nasce na hora, com SKU `SERV-<NOME>`; troque pelo codigo do ERP no cadastro. Item sem servico nao recebe esse meta; o `starhub` do pedido nunca traz `servicos`.

```json
"line_items": [{"id": 1, "sku": "POLTRONA-001", "meta_data": [
  {"id": 1, "key": "starhub", "value": {"servicos": [
    {"id": 1, "nome": "Impermeabilização da poltrona",
     "sku": "SERV-IMPERMEABILIZACAO-DA-POLTRONA", "preco": "499.99", "opcao": "Sim"}]}}]}]
```

No PUT (e no `update` do batch) o ERP pode devolver o item como recebeu: os servicos do `starhub` do item trocam os daquele item, sem duplicar; `id` e `sku` sao ignorados na entrada (vem do cadastro). `nome` (ou `servico`, do formato anterior) diz qual e o servico. `"servicos": []` tira os servicos do item. Item que nao manda `starhub` nem EPOFW no `meta_data` mantem os servicos que tinha.

## Formato antigo aceito na entrada

O ERP pode enviar metadados no formato antigo (chaves soltas). StarHub aceita e converte automaticamente para o novo formato `starhub`:

- `_shopify_order_id` -> origem.id
- `_shopify_order_number` -> origem.numero
- `_shopify_name` -> origem.nome
- `_shopify_order_url` -> origem.url
- `_shopify_financial_status` -> origem.status_financeiro
- `_shopify_updated_at` -> origem.atualizado_em
- `_billing_cpf` -> cliente.cpf
- `_billing_persontype` -> cliente.tipo_pessoa
- `delivery_date` -> entrega.agendamento
- `delivery_type` -> entrega.tipo
- `_shopify_coupon_codes` -> cupons (converte virgula para lista)

Tambem continuam aceitos:

- `starhub.servicos` no `meta_data` do **pedido**, com `item_id` em cada servico (troca a lista inteira).
- Servicos EPOFW no `meta_data` do item (chave `epofw_field_*`). Viram servico daquele item; opcao "Não" tira o servico. Se o item mandar `starhub` e EPOFW juntos, vale o `starhub`.

```json
{"key": "epofw_field_55", "value": "{\"epofw_field_55\": {\"epofw_label\": \"IMPERMEABILIZAÇÃO:\", \"epofw_value\": \"Sim\", \"epofw_price\": 499.99}}"}
```

vira, no GET, `{"id": 1, "nome": "Impermeabilização da poltrona", "sku": "SERV-IMPERMEABILIZACAO-DA-POLTRONA", "preco": "499.99", "opcao": "Sim"}` dentro do `starhub` do item.

## Criacao de categoria e cupom

- **Categoria**: se o produto tem uma categoria que nao existe em StarHub, ela e criada pelo nome
- **Tag**: tags do produto tambem sao criadas pelo nome quando nao existem
- **Id inexistente**: categoria ou tag enviada so por `id` que nao existe (sem nome) e ignorada, sem erro
- **Cupom**: identificado pelo nome (unico por conta), com codigo interno aleatorio. Do Shopify, o hub consulta o desconto e cria o cupom completo, com nome igual ao titulo do desconto (no exemplo acima, "Black Friday 10%"); se o Shopify nao conhece o codigo, nasce ativo com nome igual ao codigo. Do ERP (`coupon_lines` desconhecido em PUT), nasce pelo nome igual ao codigo, em rascunho (`status` "draft") para ser conferido

## Exemplo JSON completo

Veja [docs/pedido-json-erp.md](pedido-json-erp.md): o JSON completo do pedido explicado campo por campo. O mesmo JSON fica em [docs/exemplos/pedido-completo.json](exemplos/pedido-completo.json); os dois sao conferidos por teste contra a resposta real da API (`apps/woo_api/tests/test_doc_pedido_json.py`).
