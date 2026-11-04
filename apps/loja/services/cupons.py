"""Elegibilidade do cupom para itens e para o pedido inteiro.

    itens_elegiveis(cupom, pedido.itens.all())  -> os itens que recebem o desconto
    pedido_elegivel(cupom, pedido)              -> datas e limites do carrinho
"""

from django.utils import timezone
from django.utils.dateparse import parse_time

from apps.loja.models import Cupom

Regra = Cupom.ElegibilidadeProduto


def _categorias_de(produto):
    ids = set(produto.categorias.values_list("pk", flat=True))
    return ids | ({produto.categoria_id} if produto.categoria_id else set())


def em_promocao(variante):
    """Preco promocional valendo agora (dentro do periodo, se houver)."""
    return variante.sale_price is not None and variante.current_price == variante.sale_price


def _na_faixa(valor, minimo, maximo):
    return not ((minimo is not None and valor < minimo)
                or (maximo is not None and valor > maximo))


def vale_para(cupom, variante, preco=None):
    produto = variante.produto
    categorias = _categorias_de(produto)
    preco = variante.current_price if preco is None else preco
    if not _na_faixa(preco, cupom.preco_item_minimo, cupom.preco_item_maximo):
        return False
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
    return [item for item in itens if item.variante_id and vale_para(
        cupom, item.variante, item.preco_unitario)]


def _horario(cupom, momento):
    inicio = cupom.horario_inicio
    fim = cupom.horario_fim
    inicio = parse_time(inicio) if isinstance(inicio, str) else inicio
    fim = parse_time(fim) if isinstance(fim, str) else fim
    atual = momento.time().replace(tzinfo=None)
    if inicio and fim and inicio > fim:  # ex.: 22:00 ate 06:00
        return atual >= inicio or atual <= fim
    return not ((inicio and atual < inicio) or (fim and atual > fim))


def _dia_permitido(cupom, momento):
    if not cupom.dias_semana:
        return True
    inicio = cupom.horario_inicio
    fim = cupom.horario_fim
    inicio = parse_time(inicio) if isinstance(inicio, str) else inicio
    fim = parse_time(fim) if isinstance(fim, str) else fim
    dia = momento.weekday()
    # Na faixa 22:00-06:00, terca 02:00 ainda pertence a campanha de segunda.
    if inicio and fim and inicio > fim and momento.time().replace(tzinfo=None) <= fim:
        dia = (dia - 1) % 7
    return str(dia) in cupom.dias_semana


def _produtos_distintos(itens):
    return len({item.produto_id or ("variante", item.variante_id) for item in itens})


def pedido_elegivel(cupom, pedido, agora=None):
    """Confere as regras do carrinho; produto/preco de cada linha ficam em `vale_para`."""
    agora = agora or timezone.now()
    if timezone.is_naive(agora):
        agora = timezone.make_aware(agora)
    local = timezone.localtime(agora)
    if cupom.status != Cupom.Status.ATIVO:
        return False
    if cupom.starts_at and agora < cupom.starts_at:
        return False
    if cupom.ends_at and agora >= cupom.ends_at:
        return False
    if not _dia_permitido(cupom, local):
        return False
    if not _horario(cupom, local):
        return False
    subtotal = pedido.subtotal
    requisito = cupom.minimum_requirement
    if requisito in (Cupom.RequisitoMinimo.SUBTOTAL, Cupom.RequisitoMinimo.AMBOS):
        if subtotal < cupom.minimum_subtotal:
            return False
    if cupom.subtotal_maximo is not None and subtotal > cupom.subtotal_maximo:
        return False
    itens = list(pedido.itens.all())
    quantidade = sum(item.quantidade for item in itens)
    if requisito in (Cupom.RequisitoMinimo.QUANTIDADE, Cupom.RequisitoMinimo.AMBOS):
        if quantidade < cupom.minimum_quantity:
            return False
    if cupom.quantidade_maxima is not None and quantidade > cupom.quantidade_maxima:
        return False
    distintos = _produtos_distintos(itens)
    if (cupom.produtos_distintos_minimos is not None
            and distintos < cupom.produtos_distintos_minimos):
        return False
    if (cupom.produtos_distintos_maximos is not None
            and distintos > cupom.produtos_distintos_maximos):
        return False
    return True
