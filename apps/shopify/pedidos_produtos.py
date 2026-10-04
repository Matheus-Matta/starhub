"""Garante o produto de um item de pedido Shopify que o hub ainda nao conhece.

O produto e importado pelo caminho normal (`recursos.produto`), com variantes,
precos e imagens: um cadastro minimo feito a partir do item ficaria sem as
outras variantes e divergiria do Shopify na proxima sincronizacao.
"""

import logging

from apps.core.models import ExternalReference, Origin
from apps.loja.models import Produto, VarianteProduto
from apps.shopify.cliente import ShopifyClient
from apps.shopify.consultas_produtos import CONSULTA_PRODUTO
from apps.shopify.contexto import configuracao_atual

logger = logging.getLogger(__name__)


def _referencia(entidade, externo_id):
    return ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type=entidade, external_id=externo_id
    ).first()


def _variante_do_produto(produto, variante_gid, sku):
    referencia = _referencia("variantes", variante_gid) if variante_gid else None
    variante = produto.variantes.filter(pk=referencia.object_id).first() if referencia else None
    if variante is None and sku:
        variante = produto.variantes.filter(sku=sku).first()
    return variante or produto.variante_padrao


def _procurar(produto_gid, variante_gid, sku):
    referencia = _referencia("produtos", produto_gid) if produto_gid else None
    produto = Produto.objects.filter(pk=referencia.object_id).first() if referencia else None
    if produto:
        return _variante_do_produto(produto, variante_gid, sku)
    referencia = _referencia("variantes", variante_gid) if variante_gid else None
    if referencia:
        variante = VarianteProduto.objects.filter(pk=referencia.object_id).first()
        if variante:
            return variante
    return VarianteProduto.objects.filter(sku=sku).first() if sku else None


def garantir_produto(linha):
    """Devolve a variante do item, importando o produto do Shopify se preciso.

    Erro de rede/API sobe de proposito: a execucao falha e pode ser reprocessada,
    em vez de gravar o pedido com item solto para sempre.
    """
    produto_id, variante_id = linha.get("product_id"), linha.get("variant_id")
    produto_gid = f"gid://shopify/Product/{produto_id}" if produto_id else None
    variante_gid = f"gid://shopify/ProductVariant/{variante_id}" if variante_id else None
    sku = linha.get("sku") or ""
    variante = _procurar(produto_gid, variante_gid, sku)
    if variante or not produto_gid:
        if not variante:
            logger.info("Item %s sem produto no Shopify; fica solto.", linha.get("id"))
        return variante
    configuracao = configuracao_atual()
    if configuracao is None:
        logger.warning("Sem loja Shopify no contexto para buscar %s; item fica solto.",
                       produto_gid)
        return None
    node = ShopifyClient(configuracao).graphql(CONSULTA_PRODUTO, {"id": produto_gid})
    node = node.get("product")
    if not node:
        logger.warning("Produto %s nao existe mais no Shopify; item fica solto.", produto_gid)
        return None
    # Import tardio: recursos importa pedidos, que chama este modulo.
    from apps.shopify.recursos import produto as importar_produto

    produto, _criado = importar_produto(node)
    return _variante_do_produto(produto, variante_gid, sku)
