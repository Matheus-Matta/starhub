from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTAVO = Decimal("0.01")


def moeda(valor, simbolo="R$"):
    """Decimal em reais no formato brasileiro: 1234.5 -> "R$ 1.234,50".

    Nao usa locale do sistema operacional: o servidor pode estar em ingles.
    """
    try:
        numero = Decimal(str(valor if valor not in (None, "") else 0))
    except InvalidOperation:
        return valor
    numero = numero.quantize(CENTAVO, rounding=ROUND_HALF_UP)
    inteiro, centavos = f"{abs(numero):,.2f}".split(".")
    texto = f"{inteiro.replace(',', '.')},{centavos}"
    sinal = "-" if numero < 0 else ""
    return f"{sinal}{simbolo} {texto}".strip()


TONS_STATUS = {
    # Pedido
    "pending": "warning",
    "processing": "primary",
    "on-hold": "warning",
    "completed": "success",
    "cancelled": "secondary",
    "refunded": "info",
    "failed": "destructive",
    "trash": "secondary",
    # Produto
    "publish": "success",
    "draft": "secondary",
    "private": "info",
    # Estoque
    "instock": "success",
    "outofstock": "destructive",
    "onbackorder": "warning",
}


def tom_status(status):
    return TONS_STATUS.get(status, "secondary")
