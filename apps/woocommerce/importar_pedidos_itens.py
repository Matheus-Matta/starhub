"""Itens e linhas (frete, taxas, cupons) do pedido WooCommerce no pedido do hub.

O id do line_item fica no vinculo "itens_pedido": o order.updated acha o item certo
em vez de criar outro. O produto que o hub ainda nao conhece e buscado na loja e
importado inteiro (o mesmo caminho da sincronizacao), nunca um cadastro minimo.
"""

from apps.loja.dinheiro import ZERO, texto
from apps.loja.models import ItemPedido, Produto, VarianteProduto
from apps.loja.totais import valores_do_item
from apps.woocommerce import vinculos
from apps.woocommerce.importar_catalogo import preco

ENTIDADE = "itens_pedido"


def _buscar_na_loja(produto_id):
    """Importa o produto da loja; None sem loja na execucao (ex.: teste sem cliente)."""
    from apps.woocommerce.contexto import configuracao_atual
    from apps.woocommerce.sincronizar_produtos import importar_da_loja

    configuracao = configuracao_atual()
    return importar_da_loja(configuracao, produto_id) if configuracao else None


def variante_da_linha(linha):
    """Variacao pelo vinculo -> produto pelo vinculo -> SKU -> busca na loja."""
    variacao, produto_id = linha.get("variation_id") or 0, linha.get("product_id") or 0
    if variacao:
        variante = vinculos.existente("variantes", VarianteProduto, variacao)
        if variante:
            return variante
    produto = vinculos.existente("produtos", Produto, produto_id) if produto_id else None
    if produto and not variacao:
        return produto.variante_padrao
    sku = str(linha.get("sku") or "").strip()
    variante = VarianteProduto.objects.filter(sku=sku).first() if sku else None
    if variante or not produto_id:
        return variante
    # Erro da loja sobe de proposito: o pedido inteiro volta e a tarefa fica para retomar.
    _buscar_na_loja(produto_id)
    if variacao:
        return vinculos.existente("variantes", VarianteProduto, variacao)
    produto = vinculos.existente("produtos", Produto, produto_id)
    return produto.variante_padrao if produto else None


def _gravar(item, linha):
    variante = variante_da_linha(linha)
    quantidade = max(int(linha.get("quantity") or 1), 1)
    unitario = preco(linha.get("price")) or ZERO
    item.variante = variante
    item.produto = variante.produto if variante else None
    item.id_variacao = variante.pk if item.produto and \
        item.produto.tipo == Produto.Tipo.VARIAVEL else 0
    item.nome = str(linha.get("name") or "")[:255]
    item.sku = str(linha.get("sku") or "")[:100]
    item.quantidade = quantidade
    item.preco_unitario = unitario
    # O Woo ja manda subtotal (antes do desconto) e total (depois) por linha, sem imposto.
    item.subtotal, item.total = valores_do_item(
        unitario, quantidade, preco(linha.get("subtotal")), preco(linha.get("total")))
    item.total_desconto = item.subtotal - item.total
    item.imposto_subtotal = preco(linha.get("subtotal_tax")) or ZERO
    item.imposto_total = preco(linha.get("total_tax")) or ZERO
    item.classe_fiscal = str(linha.get("tax_class") or "")[:100]
    item.save()
    vinculos.referenciar(ENTIDADE, linha.get("id"), item)
    return item


def gravar_itens(pedido, dados):
    """Cria ou atualiza os itens; o item que sumiu do pedido na loja sai do hub."""
    atuais = {str(item.pk): item for item in pedido.itens.all()}
    mantidos = set()
    for linha in dados.get("line_items") or []:
        pk = vinculos.objeto_id(ENTIDADE, linha.get("id")) if linha.get("id") else None
        item = atuais.get(str(pk)) or ItemPedido(pedido=pedido)
        mantidos.add(_gravar(item, linha).pk)
    if "line_items" in dados:
        pedido.itens.exclude(pk__in=mantidos).delete()


def _valor(linha, campo):
    return texto(preco(linha.get(campo)) or ZERO)


def linhas_frete(dados):
    return [{"id": linha.get("id") or posicao, "method_id": str(linha.get("method_id") or ""),
             "method_title": str(linha.get("method_title") or ""),
             "total": _valor(linha, "total"), "total_tax": _valor(linha, "total_tax"),
             "taxes": [], "meta_data": []}
            for posicao, linha in enumerate(dados.get("shipping_lines") or [], start=1)]


def linhas_taxa(dados):
    return [{"id": linha.get("id") or posicao, "name": str(linha.get("name") or ""),
             "tax_class": str(linha.get("tax_class") or ""),
             "tax_status": str(linha.get("tax_status") or "taxable"),
             "total": _valor(linha, "total"), "total_tax": _valor(linha, "total_tax"),
             "taxes": [], "meta_data": []}
            for posicao, linha in enumerate(dados.get("fee_lines") or [], start=1)]


def linhas_cupom(dados):
    return [{"id": linha.get("id") or posicao, "code": str(linha.get("code") or ""),
             "discount": _valor(linha, "discount"),
             "discount_tax": _valor(linha, "discount_tax"), "meta_data": []}
            for posicao, linha in enumerate(dados.get("coupon_lines") or [], start=1)]
