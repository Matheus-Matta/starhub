"""Pedido e produto no formato WooCommerce (exemplos/*.json) passam pelo hub sem
perda: o que o ERP manda e o que ele le de volta tem que bater.

Os JSON sao copias de um pedido e um produto reais com os dados pessoais trocados por
ficticios (nome, e-mail, endereco, telefone, CPF): o pedido real tem cliente de
verdade e nao pode ir para o repositorio.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from apps.loja.models import Categoria, Cliente
from apps.loja.services.variantes import criar_produto
from apps.woo_api.tests.conftest import criar_pedido

EXEMPLOS = Path(__file__).resolve().parent / "exemplos"


def _exemplo(nome):
    [dados] = json.loads((EXEMPLOS / nome).read_text(encoding="utf-8"))
    return dados


@pytest.fixture
def pedido_exemplo():
    pedido = _exemplo("orders.json")
    # O ERP manda sem os ids do Woo de origem: aqui eles apontariam para outro banco.
    for linha in pedido["line_items"]:
        quantidade = linha["quantity"]
        produto = criar_produto(linha["name"], sku=linha["sku"],
                                price=Decimal(linha["subtotal"]) / quantidade)
        linha.pop("id")
        linha["product_id"] = produto.pk
    for linha in pedido["shipping_lines"]:
        linha.pop("id")
    pedido["customer_id"] = Cliente.objects.create(email=pedido["billing"]["email"]).pk
    return pedido


def test_pedido_do_exemplo_volta_igual(api, pedido_exemplo):
    enviado = pedido_exemplo
    criado = criar_pedido(enviado)
    lido = api.get(f"/wp-json/wc/v1/orders/{criado['id']}").json()
    for campo in ("status", "currency", "total", "discount_total", "shipping_total", "total_tax",
                  "payment_method", "payment_method_title", "transaction_id", "created_via",
                  "customer_note", "date_created_gmt", "date_paid_gmt", "billing", "shipping"):
        assert lido[campo] == enviado[campo], campo
    for lido_item, item in zip(lido["line_items"], enviado["line_items"], strict=True):
        for campo in ("name", "sku", "quantity", "subtotal", "total", "price"):
            assert lido_item[campo] == item[campo], campo
    assert [(s["method_id"], s["total"]) for s in lido["shipping_lines"]] == [
        (s["method_id"], s["total"]) for s in enviado["shipping_lines"]
    ]
    # As chaves soltas do ERP viram um so campo "starhub" (recursos/pedidos_meta.py).
    antigo = {m["key"]: m["value"] for m in enviado["meta_data"]}
    [starhub] = [m["value"] for m in lido["meta_data"] if m["key"] == "starhub"]
    assert [m["key"] for m in lido["meta_data"]] == ["starhub"]
    assert starhub["origem"] == {
        "canal": "shopify",
        "id": antigo["_shopify_order_id"],
        "numero": antigo["_shopify_order_number"],
        "nome": antigo["_shopify_name"],
        "url": antigo["_shopify_order_url"],
        "status_financeiro": antigo["_shopify_financial_status"],
        "atualizado_em": antigo["_shopify_updated_at"],
    }
    assert starhub["cliente"] == {"cpf": antigo["_billing_cpf"],
                                  "tipo_pessoa": antigo["_billing_persontype"]}
    assert starhub["entrega"] == {"agendamento": antigo["delivery_date"],
                                  "tipo": antigo["delivery_type"]}


def test_produto_do_exemplo_volta_igual(api):
    enviado = _exemplo("product.json")
    enviado.pop("id")
    for categoria in enviado["categories"]:
        categoria["id"] = Categoria.objects.create(
            nome=categoria["name"], slug=categoria["slug"]
        ).pk
    resposta = api.post("/wp-json/wc/v1/products", enviado, format="json")
    assert resposta.status_code == 201, resposta.json()
    lido = api.get(f"/wp-json/wc/v1/products/{resposta.json()['id']}").json()
    for campo in ("name", "slug", "type", "status", "sku", "price", "regular_price",
                  "sale_price", "manage_stock", "stock_quantity", "stock_status", "backorders",
                  "weight", "dimensions", "categories", "description", "short_description",
                  "catalog_visibility", "tax_status", "shipping_class", "attributes"):
        assert lido[campo] == enviado[campo], campo
