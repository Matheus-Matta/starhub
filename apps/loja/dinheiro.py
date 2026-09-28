"""Dinheiro nasce arredondado aqui, uma vez so, e nunca passa por float."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")


class ValorInvalido(ValueError):
    pass


def dinheiro(valor):
    """Converte para Decimal com 2 casas (meio para cima).

    Aceita str, int e Decimal. float e recusado de proposito: 0.1 + 0.2 em float
    ja nao e 0.3, e o centavo errado aparece la na frente, no total do pedido.
    """
    if valor is None or valor == "":
        return None
    if isinstance(valor, float):
        raise ValorInvalido("Valor monetario chegou como float; envie texto ou Decimal.")
    try:
        return Decimal(str(valor).strip()).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as erro:
        raise ValorInvalido(f"Valor monetario invalido: {valor!r}") from erro


def somar(valores):
    """Soma valores JA arredondados (a regra de "total e soma dos arredondados")."""
    return sum((dinheiro(v) or ZERO for v in valores), ZERO)


def texto(valor):
    """Formato do WooCommerce para dinheiro: string com 2 casas, "" quando vazio."""
    return "" if valor is None else f"{valor:.2f}"
