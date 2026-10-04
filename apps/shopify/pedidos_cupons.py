"""Cupons do pedido Shopify: garante o Cupom no hub (apps/shopify/cupons.py) e
monta as coupon_lines do Woo.

O desconto de cada item ja vem alocado pelo Shopify (discount_allocations) e vai
para o total do item; aqui so fica o registro de qual cupom deu quanto.
"""

from apps.loja.dinheiro import ZERO, somar, texto
from apps.loja.models import Cupom
from apps.shopify.cupons import garantir_cupom
from apps.shopify.pedidos_base import valor

_TIPOS = {
    "percentage": Cupom.TipoDesconto.PERCENTUAL,
    "fixed_amount": Cupom.TipoDesconto.VALOR_FIXO,
    "shipping": Cupom.TipoDesconto.FRETE_GRATIS,
}


def _alocado(dados, indice):
    """Quanto a aplicacao `indice` descontou somando itens e fretes."""
    linhas = [*(dados.get("line_items") or []), *(dados.get("shipping_lines") or [])]
    return somar(
        aloc.get("amount") for linha in linhas for aloc in linha.get("discount_allocations") or []
        if aloc.get("discount_application_index") == indice
    )


def _aplicacoes(dados):
    return [(indice, app) for indice, app in enumerate(dados.get("discount_applications") or [])
            if app.get("code")]


def codigos_do_pedido(dados):
    """[(code, tipo do Shopify, desconto)] de discount_codes; sem eles, das aplicacoes."""
    codigos = [
        (str(item["code"]).strip(), item.get("type") or "fixed_amount", valor(item.get("amount")))
        for item in dados.get("discount_codes") or [] if item.get("code")
    ]
    if codigos:
        return codigos
    return [
        (str(app["code"]).strip(),
         "shipping" if app.get("target_type") == "shipping_line"
         else app.get("value_type") or "fixed_amount",
         _alocado(dados, app.get("index", indice)))
        for indice, app in _aplicacoes(dados)
    ]


def _valor_do_cupom(dados, codigo, desconto):
    """O valor do cupom (10 de "10%") esta na aplicacao; o discount_codes traz o desconto."""
    for _indice, app in _aplicacoes(dados):
        if app["code"].casefold() == codigo.casefold():
            return valor(app.get("value"))
    return desconto


def _padrao(dados, codigo, tipo, desconto):
    """O que o pedido diz do cupom: vale so se o Shopify nao detalhar o desconto."""
    return {
        "discount_type": _TIPOS.get(tipo, Cupom.TipoDesconto.VALOR_FIXO),
        "value": _valor_do_cupom(dados, codigo, desconto) or ZERO,
        "free_shipping": tipo == "shipping",
    }


def gravar_cupons(pedido, dados):
    """Grava linhas_cupom (sem salvar) e devolve os codigos usados."""
    linhas = []
    for posicao, (codigo, tipo, desconto) in enumerate(codigos_do_pedido(dados), start=1):
        # A linha guarda o codigo que o cliente digitou (formato Woo); o Cupom do
        # hub e identificado pelo nome e so precisa existir.
        garantir_cupom(codigo, _padrao(dados, codigo, tipo, desconto))
        linhas.append({"id": posicao, "code": codigo, "discount": texto(desconto),
                       "discount_tax": "0.00", "meta_data": []})
    pedido.linhas_cupom = linhas
    return [linha["code"] for linha in linhas]
