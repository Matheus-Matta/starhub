"""Leitura dos campos soltos do pedido REST do Shopify (ids, dinheiro, datas, atributos)."""

from django.utils.dateparse import parse_datetime

from apps.loja.dinheiro import ZERO, ValorInvalido, dinheiro, somar


def ids_do_pedido(dados):
    """(gid, id numerico em texto). O webhook manda numero; a sincronizacao, gid."""
    bruto = str(dados.get("admin_graphql_api_id") or dados.get("id") or "")
    numero = bruto.rsplit("/", 1)[-1]
    return f"gid://shopify/Order/{numero}", numero


def gid(tipo, valor):
    texto = str(valor or "")
    if not texto or texto.startswith("gid://"):
        return texto
    return f"gid://shopify/{tipo}/{texto}"


def valor(texto):
    """Dinheiro do Shopify (texto "19.90"); ausente ou lixo vira zero."""
    try:
        return dinheiro(texto if texto not in (None, "") else "0") or ZERO
    except ValorInvalido:
        return ZERO


def valor_com_fallback(item, campo, campo_set):
    """price ou price_set.shop_money.amount: a sincronizacao nem sempre traz o primeiro."""
    if item.get(campo) not in (None, ""):
        return valor(item[campo])
    return valor(((item.get(campo_set) or {}).get("shop_money") or {}).get("amount"))


def soma_alocacoes(linha):
    return somar(aloc.get("amount") for aloc in linha.get("discount_allocations") or [])


def data(texto):
    return parse_datetime(texto) if texto else None


def atributo(dados, nomes, contem=()):
    """Valor de note_attributes pelo nome (sem diferenciar maiuscula).

    `contem`: se nenhum nome bater, aceita o primeiro atributo cujo nome contem
    um desses trechos (ex.: "cpf" pega "cpf_do_comprador").
    """
    atributos = [
        (str(item.get("name") or "").strip().casefold(), str(item.get("value") or "").strip())
        for item in dados.get("note_attributes") or []
    ]
    procurados = {nome.casefold() for nome in nomes}
    for nome, texto in atributos:
        if nome in procurados and texto:
            return texto
    for nome, texto in atributos:
        if texto and any(trecho in nome for trecho in contem):
            return texto
    return ""
