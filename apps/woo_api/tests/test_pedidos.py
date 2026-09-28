from decimal import Decimal

import pytest

from apps.loja.models import Cliente, Pedido
from apps.loja.services.variantes import criar_produto

URL = "/wp-json/wc/v1/orders"


@pytest.fixture
def produto(db):
    return criar_produto("Caneca", sku="CAN-1", price=Decimal("10.05"))


def test_pedido_calcula_totais_pelo_preco_do_produto(api, produto):
    corpo = api.post(URL, {
        "payment_method": "pix",
        "line_items": [{"product_id": produto.pk, "quantity": 2}],
        "shipping_lines": [{"method_id": "flat_rate", "method_title": "Sedex", "total": "15"}],
    }, format="json").json()
    assert corpo["line_items"][0]["subtotal"] == "20.10"
    assert corpo["line_items"][0]["sku"] == "CAN-1"
    assert corpo["shipping_total"] == "15.00"
    assert corpo["total"] == "35.10"
    assert corpo["status"] == "pending"
    assert corpo["number"] == str(corpo["id"])


def test_desconto_por_item_entra_no_total(api, produto):
    corpo = api.post(URL, {"line_items": [
        {"product_id": produto.pk, "quantity": 1, "subtotal": "10.05", "total": "9.05"},
        {"product_id": produto.pk, "quantity": 1, "subtotal": "10.05", "total": "9.05"},
    ]}, format="json").json()
    assert (corpo["total"], corpo["discount_total"]) == ("18.10", "2.00")


def test_set_paid_passa_para_processando_e_marca_data(api, produto):
    cliente = Cliente.objects.create(email="a@b.test")
    corpo = api.post(URL, {"customer_id": cliente.pk, "set_paid": True,
                           "line_items": [{"product_id": produto.pk, "quantity": 1}]},
                     format="json").json()
    assert corpo["status"] == "processing"
    assert corpo["date_paid"] is not None
    cliente.refresh_from_db()
    assert cliente.cliente_pagante is True


def test_concluir_marca_data_de_conclusao(api, produto):
    pedido = api.post(URL, {"line_items": [{"product_id": produto.pk}]}, format="json").json()
    corpo = api.put(f"{URL}/{pedido['id']}", {"status": "completed"}, format="json").json()
    assert corpo["date_completed"] and corpo["date_paid"]


def test_produto_inexistente_no_item_e_recusado_sem_criar_pedido(api):
    resposta = api.post(URL, {"line_items": [{"product_id": 999, "quantity": 1}]},
                        format="json")
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "woocommerce_rest_invalid_product_id"
    assert not Pedido.objects.exists()  # a transacao desfez o pedido pela metade


def test_cliente_inexistente_e_recusado(api):
    resposta = api.post(URL, {"customer_id": 999}, format="json")
    assert resposta.json()["code"] == "woocommerce_rest_invalid_customer_id"


def test_alterar_quantidade_do_item_recalcula(api, produto):
    pedido = api.post(URL, {"line_items": [{"product_id": produto.pk, "quantity": 1}]},
                      format="json").json()
    item_id = pedido["line_items"][0]["id"]
    corpo = api.put(f"{URL}/{pedido['id']}", {"line_items": [{"id": item_id, "quantity": 3}]},
                    format="json").json()
    assert len(corpo["line_items"]) == 1
    assert corpo["total"] == "30.15"
    removido = api.put(f"{URL}/{pedido['id']}",
                       {"line_items": [{"id": item_id, "quantity": 0}]}, format="json").json()
    assert (removido["line_items"], removido["total"]) == ([], "0.00")


def test_filtro_por_status_e_por_cliente(api, produto):
    cliente = Cliente.objects.create(email="a@b.test")
    Pedido.objects.create(status="processing", cliente=cliente)
    Pedido.objects.create(status="completed")
    Pedido.objects.create(status="trash")
    assert len(api.get(URL).json()) == 2  # "any" nao traz a lixeira
    assert [p["status"] for p in api.get(f"{URL}?status=processing").json()] == ["processing"]
    assert len(api.get(f"{URL}?customer={cliente.pk}").json()) == 1


def test_datas_no_formato_woo_com_e_sem_gmt(api, produto):
    corpo = api.post(URL, {"date_created_gmt": "2026-09-27T13:00:00"}, format="json").json()
    assert corpo["date_created_gmt"] == "2026-09-27T13:00:00"
    assert corpo["date_created"] == "2026-09-27T10:00:00"  # America/Sao_Paulo


def test_item_aponta_para_a_variante_e_guarda_o_que_foi_vendido(api, produto):
    """Pedido e documento historico: mudar SKU e preco depois nao mexe no item vendido."""
    corpo = api.post(URL, {"line_items": [{"product_id": produto.pk, "quantity": 1}]},
                     format="json").json()
    variante = produto.variante_padrao
    assert Pedido.objects.get(pk=corpo["id"]).itens.get().variante == variante
    variante.sku, variante.price = "NOVO", Decimal("99")
    variante.save()
    item = api.get(f"{URL}/{corpo['id']}").json()["line_items"][0]
    assert (item["sku"], item["total"]) == ("CAN-1", "10.05")


def test_endereco_do_pedido_nao_muda_com_o_cadastro_do_cliente(api):
    clientes = "/wp-json/wc/v1/customers"
    cliente = api.post(clientes, {"email": "a@b.test", "billing": {"city": "Recife"}},
                       format="json").json()
    pedido = api.post(URL, {"customer_id": cliente["id"],
                            "billing": {"city": "Recife", "cpf": "123.456.789-09"}},
                      format="json").json()
    api.put(f"{clientes}/{cliente['id']}", {"billing": {"city": "Olinda"}}, format="json")
    billing = api.get(f"{URL}/{pedido['id']}").json()["billing"]
    assert (billing["city"], billing["cpf"]) == ("Recife", "123.456.789-09")


def test_transaction_id_vira_a_transacao_do_pedido(api, produto):
    corpo = api.post(URL, {"payment_method": "pix", "transaction_id": "TX-1",
                           "line_items": [{"product_id": produto.pk}]}, format="json").json()
    assert corpo["transaction_id"] == "TX-1"
    alterado = api.put(f"{URL}/{corpo['id']}", {"transaction_id": "TX-2"}, format="json").json()
    assert alterado["transaction_id"] == "TX-2"
    pagamento = Pedido.objects.get(pk=corpo["id"]).pagamentos.get()  # continua uma so
    assert (pagamento.provider, pagamento.amount) == ("pix", Decimal("10.05"))
