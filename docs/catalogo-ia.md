# Catalogo HTML para IA

O endpoint `GET /catalogo/ia/?page=1` entrega o catalogo publicavel em uma tabela
HTML simples, com 1.000 itens por pagina por padrao.

Um produto variavel gera uma linha por variante. Por exemplo, `Camiseta` com as
variantes `Azul / P` e `Azul / M` aparece como:

- `Camiseta - Azul / P`, com o SKU e o preco dessa variante;
- `Camiseta - Azul / M`, com o SKU e o preco dessa variante.

Um kit gera uma linha e a coluna `Composicao do kit` lista seus componentes e
quantidades. O estoque do kit e calculado pelo componente que acaba primeiro.

## Criar a credencial

No admin, abra **Nucleo > Chaves de API** e crie uma chave com:

- permissao `Leitura`;
- escopo `catalogo_ia`;
- uma data de expiracao adequada para a integracao.

A chave `ck_...` e o segredo `cs_...` aparecem inteiros somente na criacao. Guarde-os
no cofre de segredos da ferramenta de IA.

Envie a credencial por HTTP Basic. Exemplo:

```bash
curl --user "ck_EXEMPLO:cs_EXEMPLO" \
  "https://hub.exemplo.com/catalogo/ia/?page=1&per_page=1000"
```

Nao coloque a chave e o segredo na URL. Esse endpoint recusa
`consumer_key`/`consumer_secret` na query porque URLs costumam ser gravadas em logs,
historico e proxies.

## Paginacao

A quantidade pode ser escolhida com `per_page`, de 1 a 5.000. Por exemplo,
`?page=3&per_page=250` devolve a terceira pagina com ate 250 itens. A resposta informa
`X-Catalog-Total`, `X-Catalog-Total-Pages` e `X-Catalog-Per-Page` nos cabecalhos e
inclui links HTML `rel="next"` e `rel="prev"`. A integracao deve seguir `rel="next"`
ate ele nao existir.

Somente produtos ativos, publicados e nao ocultos da conta da chave aparecem. A saida
nao inclui custo, metadados internos, rascunhos ou produtos de outra conta.
Uma chave com o escopo `catalogo_ia` e exclusiva desta rota e nao abre as rotas da API
Woo de produtos, pedidos, clientes ou categorias.

## Protecoes

Qualquer pessoa ou sistema que possua a chave consegue ler o catalogo; nao existe uma
forma tecnica de distinguir uma IA de uma pessoa. A protecao real e a chave dedicada,
de somente leitura e com expiracao. Alem disso, o endpoint:

- limita cada chave a 120 requisicoes por minuto;
- impede cache e indexacao por buscadores;
- escapa todo conteudo cadastrado antes de montar o HTML;
- bloqueia scripts, frames e carregamento de recursos externos;
- aceita somente a credencial no cabecalho `Authorization`.
