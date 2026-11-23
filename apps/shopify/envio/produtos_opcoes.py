"""Produto simples na loja que virou variavel no hub: troca a opcao padrao pela do hub.

Na loja o produto simples tem so a opcao "Title" (valor "Default Title"). Quando o hub
agrupa simples num variavel (loja/services/agrupar.py), o update manda variantes com
"Tamanho", que a loja nao tem: `produtos_casar.criaveis` deixava todas de fora e o
produto da loja seguia simples. O productOptionsCreate substitui o "Title" (e o
marcador de produto sem opcao) e, com LEAVE_AS_IS, a variante que ja existe recebe o
primeiro valor de cada opcao. Por isso a opcao vai so com os valores da variante do
hub ligada a ela; as outras variantes trazem os seus valores no create.

    opcoes = trocar_padrao(enviador, gid, variantes, loja, vinculos, opcoes)
"""

from apps.shopify.envio import produtos_variantes as variantes_shopify

CRIAR_OPCOES = """mutation($productId: ID!, $options: [OptionCreateInput!]!,
    $variantStrategy: ProductOptionCreateVariantStrategy) {
  productOptionsCreate(productId: $productId, options: $options,
                       variantStrategy: $variantStrategy) {
    product { id options { name } }
    userErrors { field message }
  }
}"""


def trocar_padrao(enviador, produto_gid, variantes, loja, vinculos, opcoes):
    """Nomes das opcoes do produto da loja depois da troca (ou os de antes, sem troca)."""
    if opcoes != {variantes_shopify.OPCAO_PADRAO} or len(variantes) < 2 or len(loja) != 1:
        return opcoes
    dona = next((v for v in variantes if vinculos.get(str(v.pk)) == loja[0]["id"]), None)
    if dona is None or not dona.opcoes.exists():
        # Variavel sem opcao cadastrada segue no "Title" pelo titulo (produtos_variantes).
        return opcoes
    pares = variantes_shopify.opcoes_da_variante(dona, True)
    resposta = enviador.mutacao(CRIAR_OPCOES, {
        "productId": produto_gid,
        "options": [{"name": nome, "position": posicao, "values": [{"name": valor}]}
                    for posicao, (nome, valor) in enumerate(pares, 1)],
        "variantStrategy": "LEAVE_AS_IS",
    }, "productOptionsCreate")
    nomes = {o.get("name") for o in ((resposta.get("product") or {}).get("options") or [])}
    return nomes or {nome for nome, _valor in pares}
