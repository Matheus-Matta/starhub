# Catalogo HTML publico para IA

Cada conta decide se publica seu catalogo em **Nucleo > Minha conta**, na secao
**Catalogo publico para IA**. Desligado, o endereco responde 404. Ligado, qualquer
pessoa ou sistema com o link consegue ler os produtos publicados, sem usuario ou
senha.

O link aparece na propria tela da conta e segue este formato:

```text
https://dominio-do-hub.com/<uuid-da-conta>/catalogo/public/?page=1&per_page=1000
```

O UUID identifica a conta. Ele nao e uma senha: o controle de publicacao e o switch
da tela **Minha conta**.

## Conteudo

Um produto variavel gera uma linha por variante. Por exemplo, `Camiseta` com as
variantes `Azul / P` e `Azul / M` aparece como:

- `Camiseta - Azul / P`, com o SKU e o preco dessa variante;
- `Camiseta - Azul / M`, com o SKU e o preco dessa variante.

Um kit gera uma linha e a coluna `Composicao do kit` lista seus componentes e
quantidades. O estoque do kit e calculado pelo componente que acaba primeiro.

Somente produtos ativos, publicados e nao ocultos aparecem. A tabela nao inclui
custo, metadados internos, rascunhos ou produtos de outra conta.

## Paginacao

Sao 1.000 itens por pagina por padrao. A quantidade pode ser escolhida com `per_page`,
de 1 a 5.000. Por exemplo, `?page=3&per_page=250` devolve a terceira pagina com ate
250 itens.

A resposta informa `X-Catalog-Total`, `X-Catalog-Total-Pages` e
`X-Catalog-Per-Page` nos cabecalhos e inclui links HTML `rel="next"` e `rel="prev"`.
A integracao deve seguir `rel="next"` ate ele nao existir.

## Protecoes

- a conta precisa estar ativa e com a publicacao ligada;
- o UUID da URL define exatamente um tenant;
- cada IP pode fazer ate 120 requisicoes por minuto;
- desligar a publicacao retira o acesso sem depender de cache;
- buscadores recebem instrucao para nao indexar a pagina;
- todo conteudo cadastrado e escapado antes de entrar no HTML;
- scripts, frames e carregamento de recursos externos ficam bloqueados.
