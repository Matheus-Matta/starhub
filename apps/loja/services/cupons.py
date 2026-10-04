"""Para quais itens o cupom vale: a elegibilidade de produto (todos, produtos,
variantes, categorias ou tags) e, por cima dela, as excecoes (produtos e
categorias excluidos, itens em promocao).

    itens_elegiveis(cupom, pedido.itens.all())  -> os itens que recebem o desconto
"""

from apps.loja.models import Cupom

Regra = Cupom.ElegibilidadeProduto


def _categorias_de(produto):
    ids = set(produto.categorias.values_list("pk", flat=True))
    return ids | ({produto.categoria_id} if produto.categoria_id else set())


def em_promocao(variante):
    """Preco promocional valendo agora (dentro do periodo, se houver)."""
    return variante.sale_price is not None and variante.current_price == variante.sale_price


def vale_para(cupom, variante):
    produto = variante.produto
    categorias = _categorias_de(produto)
    if cupom.excluir_promocao and em_promocao(variante):
        return False
    if cupom.produtos_excluidos.filter(pk=produto.pk).exists():
        return False
    if cupom.categorias_excluidas.filter(pk__in=categorias).exists():
        return False
    regra = cupom.product_eligibility
    if regra == Regra.PRODUTOS:
        return cupom.produtos.filter(pk=produto.pk).exists()
    if regra == Regra.VARIANTES:
        return cupom.variantes.filter(pk=variante.pk).exists()
    if regra == Regra.CATEGORIAS:
        return cupom.categorias.filter(pk__in=categorias).exists()
    if regra == Regra.TAGS:
        return cupom.tags.filter(pk__in=produto.tags.values("pk")).exists()
    return True


def itens_elegiveis(cupom, itens):
    """Itens de pedido (ou qualquer objeto com `variante`) que recebem o desconto."""
    return [item for item in itens if item.variante_id and vale_para(cupom, item.variante)]
