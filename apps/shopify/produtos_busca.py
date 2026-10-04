"""Busca no Shopify o produto completo, um por id.

O webhook products/create e products/update nao traz SEO nem colecoes, e a pagina
da sincronizacao corta variantes, colecoes e fotos (consultas_produtos.py): nos dois casos
o produto e lido de novo, inteiro, pela consulta de um produto.
Erro de rede/API sobe de proposito: a execucao falha e pode ser reprocessada, em vez
de gravar o produto pela metade (como em pedidos_produtos.garantir_produto).
"""

from apps.shopify.cliente import ShopifyClient
from apps.shopify.consultas_produtos import CONSULTA_PRODUTO
from apps.shopify.contexto import configuracao_atual


def buscar_produto(produto_gid):
    """No completo do produto, ou None sem loja no contexto ou se ele sumiu da loja."""
    configuracao = configuracao_atual()
    if configuracao is None or not produto_gid:
        return None
    dados = ShopifyClient(configuracao).graphql(CONSULTA_PRODUTO, {"id": produto_gid})
    return (dados or {}).get("product")


def _cortado(dados, campo):
    return bool(((dados.get(campo) or {}).get("pageInfo") or {}).get("hasNextPage"))


def completar(dados):
    """Produto da pagina em lote; inteiro de novo se alguma lista veio cortada."""
    if any(_cortado(dados, campo) for campo in ("variants", "collections", "media")):
        return buscar_produto(dados.get("id")) or dados
    return dados
