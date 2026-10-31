"""billing/shipping saem com as chaves do Woo real com o plugin Brazilian Market.

Referencia: GET /wp-json/wc/v3/orders de uma loja Woo do cliente (pedido 2000).
O ERP le campo por campo; chave que falta quebra a leitura dele.
"""

import pytest

from apps.loja.models import Cliente
from apps.woo_api.tests.conftest import criar_pedido

pytestmark = pytest.mark.django_db
URL = "/wp-json/wc/v1/orders"

BILLING_WOO = [
    "first_name", "last_name", "company", "address_1", "address_2", "city", "state",
    "postcode", "country", "email", "phone", "number", "neighborhood", "persontype", "cpf",
    "rg", "cnpj", "ie", "birthdate", "gender", "cellphone",
]
SHIPPING_WOO = [
    "first_name", "last_name", "company", "address_1", "address_2", "city", "state",
    "postcode", "country", "phone", "number", "neighborhood",
]


def test_pedido_sai_com_as_chaves_do_billing_e_shipping_do_woo_na_mesma_ordem(api):
    """Sem numero, bairro e tipo de pessoa o ERP montava o cliente sem esses campos."""
    pedido = criar_pedido({"billing": {"city": "Recife"}, "shipping": {"city": "Recife"}})
    corpo = api.get(f"{URL}/{pedido['id']}").json()
    assert list(corpo["billing"]) == BILLING_WOO
    assert list(corpo["shipping"]) == SHIPPING_WOO


def test_shipping_nao_leva_cpf_nem_dados_da_pessoa(api):
    """No Woo o documento e da cobranca; repetido na entrega o ERP o lia em dobro."""
    pedido = criar_pedido({"shipping": {"city": "Recife", "cpf": "12345678909",
                                        "cnpj": "", "persontype": "1"}})
    assert list(api.get(f"{URL}/{pedido['id']}").json()["shipping"]) == SHIPPING_WOO


def test_persontype_sai_f_ou_j_como_no_woo(api):
    """O Shopify grava "1"/"2" (como o meta _billing_persontype); o billing do Woo usa F/J."""
    fisica = criar_pedido({"billing": {"cpf": "12345678909", "persontype": "1"}})
    juridica = criar_pedido({"billing": {"cnpj": "11222333000181"}})
    assert api.get(f"{URL}/{fisica['id']}").json()["billing"]["persontype"] == "F"
    assert api.get(f"{URL}/{juridica['id']}").json()["billing"]["persontype"] == "J"


def test_cpf_vazio_no_endereco_usa_o_do_cadastro_do_cliente(api):
    """Pedido do Shopify sem documento no checkout: o CPF do cliente ja esta no hub."""
    cliente = Cliente.objects.create(email="a@b.test", cpf="12345678909")
    pedido = criar_pedido({"customer_id": cliente.pk, "billing": {"city": "Recife"}})
    billing = api.get(f"{URL}/{pedido['id']}").json()["billing"]
    assert (billing["cpf"], billing["persontype"]) == ("12345678909", "F")


def test_cliente_da_api_sai_com_o_mesmo_billing_do_woo(api):
    corpo = api.post("/wp-json/wc/v1/customers", {"email": "a@b.test"}, format="json").json()
    assert list(corpo["billing"]) == BILLING_WOO
    assert list(corpo["shipping"]) == SHIPPING_WOO
