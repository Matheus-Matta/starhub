"""Categorias do produto no hub -> colecoes do produto no Shopify.

O envio de categoria (categorias.py) cria a colecao, mas nunca manda `products`: quem
liga o produto a colecao e o envio do produto, e ele nao fazia isso. O produto ia para
a loja sem colecao nenhuma.

collectionAddProducts, uma colecao por chamada: colecao automatica (por regra) recusa
produto incluido a mao, e essa recusa nao pode derrubar as outras nem o envio. So entra:
colecao que o produto ja tem na loja e nao tem no hub fica (pode ter sido posta la).
"""

import logging

from apps.core.models import ExternalReference
from apps.shopify.cliente import ShopifyErro

logger = logging.getLogger(__name__)

ADICIONAR = """mutation($id: ID!, $productIds: [ID!]!) {
  collectionAddProducts(id: $id, productIds: $productIds) { userErrors { field message } }
}"""


def _vinculos(enviador, produto):
    categorias = {str(c.pk): c.nome for c in produto.categorias.all()}
    ligadas = dict(ExternalReference.all_objects.filter(
        account_id=enviador.configuracao.account_id, platform=enviador.plataforma,
        entity_type="categorias", object_id__in=list(categorias),
    ).values_list("object_id", "external_id"))
    sem_vinculo = [nome for pk, nome in categorias.items() if pk not in ligadas]
    return [enviador.gid("Collection", gid) for gid in ligadas.values()], sem_vinculo


def da_resposta(produto):
    """Gids das colecoes que o produto ja tem na loja (resposta do productUpdate)."""
    return {n["id"] for n in (((produto or {}).get("collections") or {}).get("nodes") or [])}


def entrar(enviador, produto, produto_gid, atuais=()):
    colecoes, sem_vinculo = _vinculos(enviador, produto)
    if sem_vinculo:
        logger.warning(
            "Produto %s: categoria(s) %s sem colecao na Shopify; ligue Enviar > Categorias "
            "> Criar (ou sincronize as categorias) e envie o produto de novo.",
            produto.pk, ", ".join(sorted(sem_vinculo)))
    for colecao in sorted(set(colecoes) - set(atuais)):
        try:
            enviador.mutacao(ADICIONAR, {"id": colecao, "productIds": [produto_gid]},
                             "collectionAddProducts")
        except ShopifyErro as erro:
            logger.warning("Produto %s nao entrou na colecao %s da Shopify (%s); colecao "
                           "automatica so aceita produto pelas regras dela.",
                           produto.pk, colecao, erro)
