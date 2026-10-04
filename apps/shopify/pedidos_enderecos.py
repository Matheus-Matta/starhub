"""Enderecos do pedido Shopify no formato Woo, com CPF, numero e bairro brasileiros.

    address1 "Rua das Flores, 100"   -> address_1 "Rua das Flores", number "100"
    address2 "Apto 10, Centro"       -> neighborhood "Centro"
    note_attributes customer_document -> cpf "12345678900", persontype "1"
"""

import re

from apps.core.models import Address
from apps.loja.services.enderecos import COLUNAS
from apps.loja.services.pedidos import gravar_endereco_do_pedido
from apps.loja.validators import somente_digitos
from apps.shopify.pedidos_base import atributo

_NUMERO_NO_FIM = re.compile(r"^(?P<rua>.*?)[,\s]+(?:n[º°o.]*\s*)?(?P<numero>\d+[a-zA-Z]?)\s*$")


def documento(dados):
    bruto = atributo(dados, ("customer_document", "cpf", "billing_cpf", "document"),
                     contem=("cpf", "document"))
    return somente_digitos(bruto)


def tipo_pessoa(doc):
    """persontype dos plugins brasileiros do Woo: 1 = fisica (CPF), 2 = juridica (CNPJ)."""
    return {11: "1", 14: "2"}.get(len(doc), "")


def _rua_e_numero(endereco1, numero):
    achado = _NUMERO_NO_FIM.match(endereco1 or "")
    if numero or not achado:
        return endereco1, numero
    return achado["rua"].strip(" ,"), achado["numero"]


def _bairro(endereco2):
    partes = [parte.strip() for parte in (endereco2 or "").split(",") if parte.strip()]
    return partes[-1] if partes else ""


def _cortado(dados):
    """O Address recusa texto maior que a coluna; do Shopify aceitamos cortado."""
    saida = {}
    for chave, texto in dados.items():
        texto = "" if texto is None else str(texto).strip()
        if chave in COLUNAS:
            texto = texto[:Address._meta.get_field(COLUNAS[chave]).max_length]
        if texto:
            saida[chave] = texto
    return saida


def endereco_woo(dados, tipo, reserva=None):
    """shipping usa a cobranca (`reserva`) para o que faltar de numero e bairro."""
    origem = dados.get(f"{tipo}_address") or {}
    if not any(origem.values()):
        return {}
    reserva = reserva or {}
    numero = atributo(dados, ("numero", "number", f"{tipo}_number"))
    rua, numero = _rua_e_numero(origem.get("address1"), numero)
    bairro = (atributo(dados, ("bairro", "neighborhood", f"{tipo}_neighborhood"))
              or _bairro(origem.get("address2")))
    woo = {
        "first_name": origem.get("first_name"), "last_name": origem.get("last_name"),
        "company": origem.get("company"), "address_1": rua,
        "address_2": origem.get("address2"), "city": origem.get("city"),
        "state": origem.get("province_code") or origem.get("province"),
        "postcode": origem.get("zip"), "country": origem.get("country_code"),
        "phone": origem.get("phone"),
        "number": numero or reserva.get("number"),
        "neighborhood": bairro or reserva.get("neighborhood"),
    }
    if tipo == "billing":
        doc = documento(dados)
        woo.update({
            "email": dados.get("email") or dados.get("contact_email"),
            "cpf" if len(doc) != 14 else "cnpj": doc, "persontype": tipo_pessoa(doc),
        })
    return _cortado(woo)


def gravar_enderecos(pedido, dados):
    """So sobrescreve o endereco quando o webhook traz o bloco preenchido."""
    cobranca = endereco_woo(dados, "billing")
    entrega = endereco_woo(dados, "shipping", reserva=cobranca)
    for tipo, woo in (("billing", cobranca), ("shipping", entrega)):
        if woo:
            gravar_endereco_do_pedido(pedido, tipo, woo)
