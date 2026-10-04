"""A busca de clientes traz o que importar_cliente le, sem campo deprecado e no limite.

Antes vinham so id, e-mail, nome, telefone, idioma e estado: o cliente chegava sem
endereco, sem consentimento de marketing e sem os contadores de compra.
"""

import re

from apps.shopify.consultas import CONSULTAS
from apps.shopify.tests.custo_graphql import custo

QUERY = CONSULTAS["clientes"][1]


def _campos_do_no(query):
    return set(re.findall(r"[A-Za-z0-9]+", query))


def test_busca_de_clientes_traz_endereco_marketing_e_contadores():
    campos = _campos_do_no(QUERY)
    esperados = {
        "defaultAddress", "addressesV2", "defaultEmailAddress", "marketingState",
        "defaultPhoneNumber", "phoneNumber", "numberOfOrders", "amountSpent", "note", "tags",
        "createdAt", "locale", "state", "taxExempt", "provinceCode", "countryCodeV2", "zip",
        "address1", "address2", "company", "hasNextPage",
    }
    assert esperados <= campos


def test_busca_de_clientes_nao_usa_campo_deprecado_na_2026_07():
    """email, phone, emailMarketingConsent e addresses estao deprecados no Customer."""
    no_do_cliente = QUERY.split("nodes {", 1)[1]
    for deprecado in ("email ", "phone ", "emailMarketingConsent", "addresses(",
                      "smsMarketingConsent"):
        assert deprecado not in no_do_cliente.replace("phoneNumber", "")


def test_busca_de_clientes_cabe_no_limite_de_custo():
    assert custo(QUERY) <= 1000
