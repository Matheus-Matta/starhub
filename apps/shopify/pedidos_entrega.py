"""Frete, agendamento e tipo de entrega do pedido Shopify."""

from apps.loja.dinheiro import ZERO, dinheiro, somar, texto
from apps.shopify.pedidos_base import atributo, soma_alocacoes, valor, valor_com_fallback

_AGENDAMENTO = ("agendamento", "delivery_date", "delivery date", "data_entrega",
                "data de entrega")
_TIPO = ("delivery_type", "tipo_entrega", "tipo de entrega", "shipping_type")


def _linha_frete(dados, linha, posicao, sozinha):
    preco = valor_com_fallback(linha, "price", "price_set")
    if not preco and sozinha:
        preco = valor(((dados.get("total_shipping_price_set") or {})
                       .get("shop_money") or {}).get("amount"))
    # Frete gratis por cupom chega como alocacao na propria linha de frete.
    total = dinheiro(max(preco - soma_alocacoes(linha), ZERO))
    imposto = ZERO if dados.get("taxes_included") else somar(
        taxa.get("price") for taxa in linha.get("tax_lines") or [])
    return {
        "id": posicao,
        "method_id": str(linha.get("code") or linha.get("source") or "")[:100],
        "method_title": str(linha.get("title") or ""),
        "total": texto(total),
        "total_tax": texto(imposto),
        "taxes": [],
        "meta_data": [],
    }


def gravar_frete(pedido, dados):
    """Refaz linhas_frete e shipping_method (sem salvar): o Shopify manda a lista toda."""
    linhas = dados.get("shipping_lines") or []
    pedido.linhas_frete = [
        _linha_frete(dados, linha, posicao, len(linhas) == 1)
        for posicao, linha in enumerate(linhas, start=1)
    ]
    pedido.shipping_method = (linhas[0].get("title") or "")[:150] if linhas else ""


def entrega_do_pedido(dados):
    """{"agendamento", "tipo"}: o tipo explicito vence; senao sai do titulo do frete."""
    tipo = atributo(dados, _TIPO).casefold()
    linhas = dados.get("shipping_lines") or []
    if not tipo and linhas:
        descricao = f"{linhas[0].get('title') or ''} {linhas[0].get('code') or ''}".casefold()
        tipo = "pickup" if "pickup" in descricao or "retirada" in descricao else "delivery"
    return {"agendamento": atributo(dados, _AGENDAMENTO), "tipo": tipo}
