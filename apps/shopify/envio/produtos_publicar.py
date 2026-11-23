"""Produto criado pelo hub entra em todos os canais de venda da loja.

O productSet cria o produto sem canal nenhum: ACTIVE, mas fora da loja virtual, do POS
e do Google ate alguem marcar os canais a mao. So na criacao: canal tirado a mao na
Shopify depois disso e escolha da loja, e o update nao o devolve.
"""

import logging

from apps.shopify.cliente import ShopifyErro

logger = logging.getLogger(__name__)

PUBLICACOES = "query { publications(first: 50) { nodes { id name } } }"
PUBLICAR = """mutation($id: ID!, $input: [PublicationInput!]!) {
  publishablePublish(id: $id, input: $input) { userErrors { field message } }
}"""


def canais(enviador):
    dados = (enviador.cliente.graphql(PUBLICACOES) or {}).get("publications") or {}
    return dados.get("nodes") or []


def em_todos(enviador, produto_gid):
    # Falha aqui nao derruba o envio: o produto ja existe na loja, e sem o vinculo o
    # proximo envio criaria um segundo produto igual.
    try:
        entrada = [{"publicationId": canal["id"]} for canal in canais(enviador)]
        if entrada:
            enviador.mutacao(PUBLICAR, {"id": produto_gid, "input": entrada},
                             "publishablePublish")
    except ShopifyErro as erro:
        logger.warning(
            "Produto %s criado na Shopify mas nao publicado nos canais (%s): confira o "
            "escopo read_publications/write_publications do app e marque os canais a mao.",
            produto_gid, erro)
