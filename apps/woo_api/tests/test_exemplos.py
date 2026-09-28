"""Pedido e produto reais (examples/*.json, formato WooCommerce) passam pelo hub
sem perda: o que o ERP manda e o que ele le de volta tem que bater."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from apps.loja.models import Categoria, Cliente
from apps.loja.services.variantes import criar_produto

EXEMPLOS = Path(__file__).resolve().parents[3] / "examples"


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
    resposta = api.post("/wp-json/wc/v1/orders", enviado, format="json")
    assert resposta.status_code == 201, resposta.json()
    lido = api.get(f"/wp-json/wc/v1/orders/{resposta.json()['id']}").json()
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
    assert {m["key"]: m["value"] for m in lido["meta_data"]} == {
        m["key"]: m["value"] for m in enviado["meta_data"]
    }


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
