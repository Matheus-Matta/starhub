"""Calculo dos valores de item e dos totais do pedido.

Regra: cada parcela nasce arredondada (item, linha de frete, taxa) e o total do
pedido e a SOMA dessas parcelas ja arredondadas. Nunca arredonde so no final:
dois itens de R$ 10,05 com 10% de desconto dao R$ 18,10 (9,05 + 9,05), e nao
o 18,09 que sairia de arredondar 20,10 x 0,9 uma vez so.
"""

from apps.loja.dinheiro import ZERO, dinheiro, somar


def valores_do_item(preco_unitario, quantidade, subtotal=None, total=None):
    """Devolve (subtotal, total) de uma linha.

    Sem subtotal informado ele vem de preco x quantidade. Sem total, o total e o
    subtotal (sem desconto). total = 0 com subtotal > 0 e desconto de 100%, nao
    "campo vazio": por isso o teste e contra None, nunca contra falsy.
    """
    if subtotal is None:
        subtotal = dinheiro((preco_unitario or ZERO) * quantidade)
    else:
        subtotal = dinheiro(subtotal)
    total = subtotal if total is None else dinheiro(total)
    return subtotal, total


def _soma_campo(linhas, campo):
    return somar(linha.get(campo) or "0" for linha in linhas or [])


def recalcular_totais(pedido, salvar=True):
    itens = list(pedido.itens.all())
    soma_subtotal = somar(item.subtotal for item in itens)
    soma_itens = somar(item.total for item in itens)
    imposto_itens = somar(item.imposto_total for item in itens)
    imposto_subtotal = somar(item.imposto_subtotal for item in itens)

    frete = _soma_campo(pedido.linhas_frete, "total")
    imposto_frete = _soma_campo(pedido.linhas_frete, "total_tax")
    taxas = _soma_campo(pedido.linhas_taxa, "total")
    imposto_taxas = _soma_campo(pedido.linhas_taxa, "total_tax")

    pedido.total_desconto = soma_subtotal - soma_itens
    pedido.imposto_desconto = imposto_subtotal - imposto_itens
    pedido.total_frete = frete
    pedido.imposto_frete = imposto_frete
    pedido.imposto_carrinho = imposto_itens + imposto_taxas
    pedido.total_impostos = pedido.imposto_carrinho + imposto_frete
    pedido.total = soma_itens + taxas + frete + pedido.total_impostos
    if salvar:
        pedido.save(
            update_fields=[
                "total_desconto", "imposto_desconto", "total_frete", "imposto_frete",
                "imposto_carrinho", "total_impostos", "total", "updated_at",
            ]
        )
    return pedido
