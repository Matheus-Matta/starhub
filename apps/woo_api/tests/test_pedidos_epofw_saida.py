"""Servicos saem tambem no formato EPOFW (epofw_field_<n>) no line_item.

O ERP foi feito para o Woo com o plugin EPOFW e le o servico dali; o "starhub"
continua saindo ao lado. Os dois sao montados dos mesmos servicos do pedido.
"""

import json
from decimal import Decimal

import pytest

from apps.loja.models import Pedido
from apps.loja.services.extras_pedido import extras
from apps.loja.services.variantes import criar_produto

URL = "/wp-json/wc/v1/orders"
IMPER = {"servico": "Impermeabilização da poltrona", "opcao": "Sim", "preco": "499.99"}


@pytest.fixture
def pedido_com_servico(db, api):
    produto = criar_produto("Poltrona Exemplo", sku="POLTRONA-001", price=Decimal("1499.90"))
    pedido = Pedido.objects.create(status="processing")
    criado = api.put(f"{URL}/{pedido.pk}", {"line_items": [
        {"product_id": produto.pk, "quantity": 2}, {"product_id": produto.pk, "quantity": 1},
    ]}, format="json").json()
    item_a, item_b = (linha["id"] for linha in criado["line_items"])
    resposta = api.put(f"{URL}/{pedido.pk}", {"meta_data": [{"key": "starhub", "value": {
        "servicos": [{"item_id": item_a, "sku": "POLTRONA-001", **IMPER}]}}]}, format="json")
    assert resposta.status_code == 200, resposta.json()
    return pedido, produto, item_a, item_b


def _itens(corpo):
    return {linha["id"]: linha for linha in corpo["line_items"]}


def _epofw(meta_data):
    return [m for m in meta_data if m["key"].startswith("epofw_field_")]


def test_get_manda_o_servico_no_formato_epofw_dentro_do_item(api, pedido_com_servico):
    """Sem o epofw_field_<n> o ERP nao ve o servico e fatura a poltrona sem ele."""
    pedido, produto, item_a, _ = pedido_com_servico
    item = _itens(api.get(f"{URL}/{pedido.pk}").json())[item_a]

    (meta,) = _epofw(item["meta_data"])
    assert isinstance(meta["value"], str), "o EPOFW grava o value como texto JSON"
    campo = json.loads(meta["value"])[meta["key"]]
    assert campo["epofw_label"] == "IMPERMEABILIZAÇÃO DA POLTRONA:"
    assert campo["epofw_value"] == "Sim"
    assert campo["epofw_price"] == campo["epofw_original_price"] == "499.99"
    assert campo["epofw_price_type"] == "fixed"
    assert campo["epofw_type"] == "radiogroup"
    assert campo["epofw_name"] == meta["key"]
    assert campo["epofw_field_quantity"] == "2"
    assert campo["product_id"] == str(produto.pk)
    opcoes = campo["epofw_form_data"]["epofw_field_settings"]["options"]
    assert opcoes == {"Sim": "Sim||fixed||499,99", "Não": "Não||fixed||0,00"}
    # O "starhub" continua saindo: quem ja le ele nao quebra.
    assert any(m["key"] == "starhub" for m in item["meta_data"])


def test_item_sem_servico_nao_ganha_epofw(api, pedido_com_servico):
    pedido, _, _, item_b = pedido_com_servico
    item = _itens(api.get(f"{URL}/{pedido.pk}").json())[item_b]
    assert _epofw(item["meta_data"]) == []


def test_ids_dos_metas_do_item_nao_se_repetem(api, pedido_com_servico):
    """Id repetido no meta_data faz o PUT seguinte do ERP alterar o meta errado."""
    pedido, _, item_a, _ = pedido_com_servico
    ids = [m["id"] for m in _itens(api.get(f"{URL}/{pedido.pk}").json())[item_a]["meta_data"]]
    assert len(ids) == len(set(ids))


def test_erp_devolvendo_so_o_epofw_nao_muda_os_servicos(api, pedido_com_servico):
    """O ERP pode reenviar so o epofw_field que recebeu: o servico tem que voltar igual."""
    pedido, _, item_a, _ = pedido_com_servico
    antes = extras(Pedido.objects.get(pk=pedido.pk))["servicos"]
    item = _itens(api.get(f"{URL}/{pedido.pk}").json())[item_a]
    meta = [{"key": m["key"], "value": m["value"]} for m in _epofw(item["meta_data"])]

    resposta = api.put(f"{URL}/{pedido.pk}", {"line_items": [
        {"id": item_a, "meta_data": meta}]}, format="json")

    assert resposta.status_code == 200, resposta.json()
    assert extras(Pedido.objects.get(pk=pedido.pk))["servicos"] == antes


def test_round_trip_com_starhub_e_epofw_juntos_nao_duplica(api, pedido_com_servico):
    pedido, _, item_a, _ = pedido_com_servico
    antes = extras(Pedido.objects.get(pk=pedido.pk))["servicos"]
    item = _itens(api.get(f"{URL}/{pedido.pk}").json())[item_a]

    resposta = api.put(f"{URL}/{pedido.pk}", {"line_items": [
        {"id": item_a, "meta_data": item["meta_data"]}]}, format="json")

    assert resposta.status_code == 200, resposta.json()
    assert extras(Pedido.objects.get(pk=pedido.pk))["servicos"] == antes
    depois = _itens(resposta.json())[item_a]["meta_data"]
    assert len(_epofw(depois)) == 1
