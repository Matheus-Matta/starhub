"""Pedido REST do webhook orders/create do Shopify, com valores que fecham a conta.

Poltrona 1499.90 - 149.99 (PROMO10) + 2 almofadas 100.00 - 10.00 + frete 39.90
= total_price 1479.81.
"""

import copy
import sys
import types

import pytest

_ENDERECO = {
    "first_name": "Maria",
    "last_name": "Silva",
    "address1": "Rua das Flores, 100",
    "address2": "Apto 10, Centro",
    "city": "São Paulo",
    "province_code": "SP",
    "zip": "01000-000",
    "country_code": "BR",
}

_PEDIDO = {
    "id": 123456789,
    "admin_graphql_api_id": "gid://shopify/Order/123456789",
    "name": "#1001",
    "order_number": 1001,
    "email": "maria@example.com",
    "phone": None,
    "currency": "BRL",
    "created_at": "2026-09-30T10:00:00-03:00",
    "processed_at": "2026-09-30T10:00:00-03:00",
    "updated_at": "2026-09-30T15:00:00-03:00",
    "cancelled_at": None,
    "financial_status": "paid",
    "fulfillment_status": None,
    "payment_gateway_names": ["appmax_pix"],
    "total_price": "1479.81",
    "subtotal_price": "1439.91",
    "total_discounts": "159.99",
    "taxes_included": False,
    "customer": {
        "id": 777,
        "admin_graphql_api_id": "gid://shopify/Customer/777",
        "email": "maria@example.com",
        "first_name": "Maria",
        "last_name": "Silva",
        "phone": "+5511999999999",
    },
    "billing_address": {**_ENDERECO, "phone": "+5511999999999"},
    "shipping_address": dict(_ENDERECO),
    "note_attributes": [
        {"name": "customer_document", "value": "123.456.789-00"},
        {"name": "Agendamento", "value": "2026-10-15"},
        {"name": "tipo_entrega", "value": "delivery"},
    ],
    "line_items": [
        {
            "id": 555,
            "title": "Poltrona Exemplo",
            "sku": "POLTRONA-001",
            "product_id": 987654321,
            "variant_id": 9001,
            "quantity": 1,
            "price": "1499.90",
            # O Shopify repete em total_discount o que ja esta nas alocacoes.
            "total_discount": "149.99",
            "discount_allocations": [{"amount": "149.99", "discount_application_index": 0}],
            "requires_shipping": True,
            "tax_lines": [],
            "properties": [
                {"name": "_impermeabilizacao_123", "value": "Sim [+ R$ 499,99]"},
                {"name": "_montagem_456", "value": "Não"},
            ],
        },
        {
            "id": 556,
            "title": "Almofada Avulsa",
            "sku": "ALMOFADA-SEM-CADASTRO",
            "product_id": 987654322,
            "variant_id": 9002,
            "quantity": 2,
            "price": "50.00",
            "total_discount": "10.00",
            "discount_allocations": [{"amount": "10.00", "discount_application_index": 0}],
            "requires_shipping": True,
            "tax_lines": [],
            "properties": [],
        },
    ],
    "shipping_lines": [
        {"id": 4001, "code": "standard", "title": "Entrega padrão", "price": "39.90",
         "discount_allocations": [], "tax_lines": []},
    ],
    "discount_codes": [{"code": "PROMO10", "amount": "159.99", "type": "percentage"}],
    "discount_applications": [{
        "type": "discount_code", "code": "PROMO10", "value": "10.0",
        "value_type": "percentage", "allocation_method": "across",
        "target_type": "line_item",
    }],
    "note": "Observação do pedido",
}


def pedido_shopify(**mudancas):
    dados = copy.deepcopy(_PEDIDO)
    dados.update(mudancas)
    return dados


@pytest.fixture
def produto_shopify_falso(monkeypatch):
    """Troca a busca do produto no Shopify (pedidos_produtos.garantir_produto, do
    braco da sincronizacao) por uma que nao acha nada e anota as linhas pedidas."""
    pedidas = []

    def garantir_produto(linha):
        pedidas.append(linha)
        return None

    falso = types.SimpleNamespace(garantir_produto=garantir_produto)
    monkeypatch.setitem(sys.modules, "apps.shopify.pedidos_produtos", falso)
    return pedidas
