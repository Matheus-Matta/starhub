"""Servicos nao saem no formato EPOFW (epofw_field_<n>) no line_item; so no "starhub".

O ERP soma o epofw_price no item, e o item ja traz o servico somado: o total
dobrava o servico. Na volta (PUT) o EPOFW ainda e aceito, para reenvio antigo.
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


def test_get_nao_manda_o_servico_no_formato_epofw(api, pedido_com_servico):
    """O ERP somava o epofw_price no item que ja tinha o servico somado: o pedido 2379
    (sofa 2199.99 + impermeabilizacao 499.99 no item) chegava com 499.99 a mais e o
    ERP recusava ("Total calculado difere do total do pedido no e-commerce")."""
    pedido, _, item_a, item_b = pedido_com_servico
    itens = _itens(api.get(f"{URL}/{pedido.pk}").json())

    assert _epofw(itens[item_a]["meta_data"]) == [] and _epofw(itens[item_b]["meta_data"]) == []
    # O servico continua no item pelo "starhub", que nao entra em soma.
    (meta,) = [m for m in itens[item_a]["meta_data"] if m["key"] == "starhub"]
    assert meta["value"]["servicos"][0]["preco"] == "499.99"


def test_ids_dos_metas_do_item_nao_se_repetem(api, pedido_com_servico):
    """Id repetido no meta_data faz o PUT seguinte do ERP alterar o meta errado."""
    pedido, _, item_a, _ = pedido_com_servico
    ids = [m["id"] for m in _itens(api.get(f"{URL}/{pedido.pk}").json())[item_a]["meta_data"]]
    assert len(ids) == len(set(ids))


def test_erp_devolvendo_so_o_epofw_nao_muda_os_servicos(api, pedido_com_servico):
    """O ERP pode reenviar o epofw_field que recebia antes: o servico tem que voltar igual."""
    pedido, _, item_a, _ = pedido_com_servico
    antes = extras(Pedido.objects.get(pk=pedido.pk))["servicos"]
    valor = {"epofw_field_1": {"epofw_label": "IMPERMEABILIZAÇÃO DA POLTRONA:",
                               "epofw_value": "Sim", "epofw_price": "499.99"}}
    meta = [{"key": "epofw_field_1", "value": json.dumps(valor, ensure_ascii=False)}]

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
