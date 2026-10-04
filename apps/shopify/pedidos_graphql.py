"""Converte o pedido da Admin GraphQL API para o JSON REST do webhook orders/create.

A sincronizacao busca via GraphQL, mas o importador de pedidos (apps.shopify.pedidos)
entende um formato so: o do webhook. Converter aqui evita dois importadores que
divergem com o tempo.
"""

import re
from collections import defaultdict

from apps.loja.dinheiro import ZERO, dinheiro, somar, texto

# O Display*Status do GraphQL tem nomes diferentes do fulfillment_status do REST.
ENTREGA_REST = {
    "FULFILLED": "fulfilled", "PARTIALLY_FULFILLED": "partial",
    "RESTOCKED": "restocked", "UNFULFILLED": None,
}
TIPO_DESCONTO = {
    "DiscountCodeApplication": "discount_code", "AutomaticDiscountApplication": "automatic",
    "ManualDiscountApplication": "manual", "ScriptDiscountApplication": "script",
}


def _id_numerico(gid):
    """O REST usa o numero do fim do gid ("gid://shopify/Order/123" -> 123)."""
    if not gid:
        return None
    final = str(gid).rsplit("/", 1)[-1]
    return int(final) if final.isdigit() else None


def _minusculo(valor):
    return valor.lower() if valor else None


def _valor(bag):
    """MoneyBag -> "19.90". O GraphQL manda "19.9"; o REST sempre tem 2 casas."""
    quantia = ((bag or {}).get("shopMoney") or {}).get("amount")
    return texto(dinheiro(quantia) if quantia not in (None, "") else ZERO)


def _conjunto(bag):
    moeda = ((bag or {}).get("shopMoney") or {}).get("currencyCode")
    return {"shop_money": {"amount": _valor(bag), "currency_code": moeda}}


def _nos(conexao):
    return (conexao or {}).get("nodes") or []


def _atributos(lista):
    return [{"name": item.get("key"), "value": item.get("value")} for item in lista or []]


def _endereco(end):
    if not end:
        return None
    nome = " ".join(p for p in (end.get("firstName"), end.get("lastName")) if p)
    return {
        "first_name": end.get("firstName"), "last_name": end.get("lastName"),
        "name": nome or None, "company": end.get("company"),
        "address1": end.get("address1"), "address2": end.get("address2"),
        "city": end.get("city"), "province": end.get("province"),
        "province_code": end.get("provinceCode"), "zip": end.get("zip"),
        "country": end.get("country"), "country_code": end.get("countryCodeV2"),
        "phone": end.get("phone"),
    }


def _alocacoes(lista):
    return [{
        "amount": _valor(item.get("allocatedAmountSet")),
        "amount_set": _conjunto(item.get("allocatedAmountSet")),
        "discount_application_index": (item.get("discountApplication") or {}).get("index"),
    } for item in lista or []]


def _item(node):
    variante, produto = node.get("variant") or {}, node.get("product") or {}
    return {
        "id": _id_numerico(node.get("id")), "admin_graphql_api_id": node.get("id"),
        "title": node.get("title"), "name": node.get("name"),
        "variant_title": node.get("variantTitle"),
        "sku": node.get("sku") or variante.get("sku") or "",
        "quantity": node.get("quantity") or 0,
        "price": _valor(node.get("originalUnitPriceSet")),
        "price_set": _conjunto(node.get("originalUnitPriceSet")),
        "total_discount": _valor(node.get("totalDiscountSet")),
        "total_discount_set": _conjunto(node.get("totalDiscountSet")),
        "discount_allocations": _alocacoes(node.get("discountAllocations")),
        "properties": _atributos(node.get("customAttributes")),
        "variant_id": _id_numerico(variante.get("id")),
        "product_id": _id_numerico(produto.get("id")),
    }


def _frete(node):
    return {
        "id": _id_numerico(node.get("id")), "code": node.get("code"),
        "title": node.get("title"), "source": node.get("source"),
        "price": _valor(node.get("originalPriceSet")),
        "price_set": _conjunto(node.get("originalPriceSet")),
        "discounted_price": _valor(node.get("discountedPriceSet")),
        "discount_allocations": _alocacoes(node.get("discountAllocations")),
    }


def _aplicacao(node):
    valor = node.get("value") or {}
    percentual = valor.get("__typename") == "PricingPercentageValue"
    # A doc do Shopify fala em faixa -100..0; o REST manda positivo ("10.0").
    numero = abs(valor.get("percentage") or 0) if percentual else valor.get("amount")
    return {
        "type": TIPO_DESCONTO.get(node.get("__typename"), "discount_code"),
        "code": node.get("code"), "index": node.get("index"),
        "value": str(numero) if numero is not None else "0",
        "value_type": "percentage" if percentual else "fixed_amount",
        "target_type": _minusculo(node.get("targetType")),
        "allocation_method": _minusculo(node.get("allocationMethod")),
    }


def _codigos(aplicacoes, itens, fretes, codigos_texto):
    """O GraphQL nao traz o valor por cupom: soma o que cada um alocou nas linhas."""
    por_indice = defaultdict(list)
    for linha in [*itens, *fretes]:
        for alocacao in linha["discount_allocations"]:
            por_indice[alocacao["discount_application_index"]].append(alocacao["amount"])
    codigos = [{
        "code": ap["code"],
        "amount": texto(somar(por_indice[ap["index"]])),
        "type": "shipping" if ap["target_type"] == "shipping_line" else ap["value_type"],
    } for ap in aplicacoes if ap["code"]]
    vistos = {item["code"] for item in codigos}
    codigos += [{"code": c, "amount": "0.00", "type": "fixed_amount"}
                for c in codigos_texto or [] if c not in vistos]
    return codigos


def _transacao(node):
    return {
        "id": _id_numerico(node.get("id")), "admin_graphql_api_id": node.get("id"),
        "kind": _minusculo(node.get("kind")), "status": _minusculo(node.get("status")),
        "gateway": node.get("gateway"), "amount": _valor(node.get("amountSet")),
        "created_at": node.get("createdAt"), "processed_at": node.get("processedAt"),
    }


def _cliente(cli):
    if not cli:
        return None
    return {
        "id": _id_numerico(cli.get("id")), "admin_graphql_api_id": cli.get("id"),
        "email": cli.get("email"), "first_name": cli.get("firstName"),
        "last_name": cli.get("lastName"), "phone": cli.get("phone"),
    }


def pedido_graphql_para_rest(node):
    itens = [_item(n) for n in _nos(node.get("lineItems"))]
    fretes = [_frete(n) for n in _nos(node.get("shippingLines"))]
    aplicacoes = [_aplicacao(n) for n in _nos(node.get("discountApplications"))]
    numero = re.sub(r"\D", "", node.get("name") or "")
    return {
        "id": int(node["legacyResourceId"]) if node.get("legacyResourceId")
        else _id_numerico(node.get("id")),
        "admin_graphql_api_id": node.get("id"),
        "name": node.get("name"), "order_number": int(numero) if numero else None,
        "email": node.get("email"), "contact_email": node.get("email"),
        "phone": node.get("phone"),
        "created_at": node.get("createdAt"), "updated_at": node.get("updatedAt"),
        "processed_at": node.get("processedAt"), "cancelled_at": node.get("cancelledAt"),
        "cancel_reason": _minusculo(node.get("cancelReason")),
        "note": node.get("note"),
        "note_attributes": _atributos(node.get("customAttributes")),
        "financial_status": _minusculo(node.get("displayFinancialStatus")),
        "fulfillment_status": ENTREGA_REST.get(
            node.get("displayFulfillmentStatus"),
            _minusculo(node.get("displayFulfillmentStatus")),
        ),
        "payment_gateway_names": list(node.get("paymentGatewayNames") or []),
        "currency": node.get("currencyCode"),
        "total_price": _valor(node.get("totalPriceSet")),
        "total_price_set": _conjunto(node.get("totalPriceSet")),
        "subtotal_price": _valor(node.get("subtotalPriceSet")),
        "total_discounts": _valor(node.get("totalDiscountsSet")),
        "total_shipping_price_set": _conjunto(node.get("totalShippingPriceSet")),
        "customer": _cliente(node.get("customer")),
        "billing_address": _endereco(node.get("billingAddress")),
        "shipping_address": _endereco(node.get("shippingAddress")),
        "line_items": itens, "shipping_lines": fretes,
        "discount_applications": aplicacoes,
        "discount_codes": _codigos(aplicacoes, itens, fretes, node.get("discountCodes")),
        "transactions": [_transacao(n) for n in node.get("transactions") or []],
    }
