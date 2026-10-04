"""meta_data do pedido na API Woo: tudo que e do StarHub fica num campo so, "starhub"."""

import json
from decimal import Decimal

import pytest

from apps.loja.models import Pedido
from apps.loja.services.extras_pedido import extras
from apps.loja.services.variantes import criar_produto

URL = "/wp-json/wc/v1/orders"


def _epofw(numero, rotulo, opcao, preco):
    chave = f"epofw_field_{numero}"
    valor = {chave: {"epofw_label": rotulo, "epofw_value": opcao, "epofw_price": preco,
                     "epofw_name": chave, "epofw_type": "radiogroup"}}
    return {"key": chave, "value": json.dumps(valor, ensure_ascii=False)}


ANTIGO = [
    {"key": "_shopify_order_id", "value": "123456789"},
    {"key": "_shopify_order_number", "value": "1001"},
    {"key": "_shopify_name", "value": "#1001"},
    {"key": "_shopify_order_url", "value": "https://loja.test/pedido"},
    {"key": "_shopify_financial_status", "value": "paid"},
    {"key": "_billing_cpf", "value": "12345678900"},
    {"key": "_billing_persontype", "value": "1"},
    {"key": "_billing_number", "value": "100"},
    {"key": "_billing_neighborhood", "value": "Centro"},
    {"key": "_shipping_number", "value": "100"},
    {"key": "_shipping_neighborhood", "value": "Centro"},
    {"key": "_shopify_updated_at", "value": "2026-09-30T15:00:00-03:00"},
    {"key": "delivery_date", "value": "2026-10-15"},
    {"key": "delivery_type", "value": "delivery"},
    {"key": "_shopify_coupon_codes", "value": "PROMO10"},
]


@pytest.fixture
def produto(db):
    return criar_produto("Poltrona Exemplo", sku="POLTRONA-001", price=Decimal("1499.90"))


@pytest.fixture
def pedido(db):
    """Pedido nao nasce pela API (so e atualizado): criado direto no banco."""
    return Pedido.objects.create(status="processing")


def _starhub(corpo):
    return next(m["value"] for m in corpo["meta_data"] if m["key"] == "starhub")


def _gravados(pedido):
    """Servicos como o banco guarda: no pedido, com item_id (a API mostra no item)."""
    pedido.refresh_from_db()
    return extras(pedido).get("servicos")


def _put(api, pedido, corpo):
    resposta = api.put(f"{URL}/{pedido.pk}", corpo, format="json")
    assert resposta.status_code == 200, resposta.json()
    return resposta.json()


def test_formato_antigo_do_md_vira_um_so_campo_starhub(api, pedido, produto):
    """O ERP antigo espalha 15 chaves soltas; o pedido guarda e devolve so o "starhub".

    Os servicos EPOFW saem do meta do item e voltam no starhub do proprio item.
    """
    corpo = _put(api, pedido, {
        "line_items": [{"product_id": produto.pk, "quantity": 1, "total": "1499.90",
                        "meta_data": [_epofw(123, "IMPERMEABILIZAÇÃO DA POLTRONA:", "Sim",
                                             "499.99")]}],
        "meta_data": ANTIGO,
    })
    item_id = corpo["line_items"][0]["id"]

    assert [m["key"] for m in corpo["meta_data"]] == ["starhub"]
    assert _starhub(corpo) == {
        "origem": {"canal": "shopify", "id": "123456789", "numero": "1001", "nome": "#1001",
                   "url": "https://loja.test/pedido", "status_financeiro": "paid",
                   "atualizado_em": "2026-09-30T15:00:00-03:00"},
        "cliente": {"cpf": "12345678900", "tipo_pessoa": "1"},
        "entrega": {"agendamento": "2026-10-15", "tipo": "delivery"},
        "cupons": ["PROMO10"],
    }
    servico = {"servico": "Impermeabilização da poltrona", "opcao": "Sim", "preco": "499.99"}
    meta_item = corpo["line_items"][0]["meta_data"]
    assert meta_item[0] == {"id": 1, "key": "starhub", "value": {"servicos": [servico]}}
    # O mesmo servico volta tambem como EPOFW (ver test_pedidos_epofw_saida.py).
    assert [m["key"] for m in meta_item[1:]] == ["epofw_field_1"]
    assert _gravados(pedido) == [{"item_id": item_id, "sku": "POLTRONA-001", **servico}]


def test_preco_numerico_no_json_do_epofw_vira_texto_com_centavos(api, pedido, produto):
    """epofw_price como numero (80.1) tem que sair "80.10", igual ao preco em texto."""
    meta = {"key": "epofw_field_7", "value": json.dumps({"epofw_field_7": {
        "epofw_label": "MONTAGEM:", "epofw_value": "Sim", "epofw_price": 80.1}})}
    corpo = _put(api, pedido, {"line_items": [{"product_id": produto.pk, "meta_data": [meta]}]})
    assert _starhub(corpo["line_items"][0])["servicos"][0]["preco"] == "80.10"
    assert _gravados(pedido)[0]["preco"] == "80.10"


def test_formato_novo_em_put_parcial_troca_so_a_secao_enviada(api, pedido):
    """PUT com so a entrega nao pode apagar a origem gravada antes."""
    _put(api, pedido, {"meta_data": [{"key": "starhub", "value": {
        "origem": {"canal": "erp", "id": "9"}, "entrega": {"agendamento": "2026-10-15"},
    }}]})

    corpo = _put(api, pedido, {"meta_data": [{"key": "starhub", "value": {
        "entrega": {"agendamento": "2026-11-01", "tipo": "pickup"},
    }}]})

    assert _starhub(corpo) == {"origem": {"canal": "erp", "id": "9"},
                               "entrega": {"agendamento": "2026-11-01", "tipo": "pickup"}}
    assert [m["key"] for m in corpo["meta_data"]] == ["starhub"]


def test_chave_antiga_solta_em_put_mescla_campo_a_campo(api, pedido):
    """delivery_type sozinho nao pode apagar o agendamento que ja estava gravado."""
    _put(api, pedido, {"meta_data": [{"key": "delivery_date", "value": "2026-10-15"}]})
    corpo = _put(api, pedido, {"meta_data": [{"key": "delivery_type", "value": "pickup"}]})
    assert _starhub(corpo) == {"entrega": {"agendamento": "2026-10-15", "tipo": "pickup"}}


def test_chave_desconhecida_fica_intacta_ao_lado_do_starhub(api, pedido):
    """So as chaves conhecidas sao dobradas; a do ERP volta no GET como veio."""
    _put(api, pedido, {"meta_data": [
        {"key": "_erp_lote", "value": {"numero": 7}},
        {"key": "delivery_date", "value": "2026-10-15"},
    ]})
    corpo = api.get(f"{URL}/{pedido.pk}").json()
    assert {m["key"]: m["value"] for m in corpo["meta_data"]} == {
        "_erp_lote": {"numero": 7}, "starhub": {"entrega": {"agendamento": "2026-10-15"}},
    }
    pedido.refresh_from_db()
    assert [m["key"] for m in pedido.metadados] == ["_erp_lote", "starhub"]


def test_servico_de_um_item_nao_apaga_o_servico_de_outro(api, pedido, produto):
    """PUT que so traz o servico do item B mantem o do item A."""
    criado = _put(api, pedido, {"line_items": [
        {"product_id": produto.pk, "meta_data": [_epofw(1, "MONTAGEM:", "Sim", "80,00")]},
        {"product_id": produto.pk},
    ]})
    item_a, item_b = (linha["id"] for linha in criado["line_items"])

    corpo = _put(api, pedido, {"line_items": [
        {"id": item_b, "meta_data": [_epofw(2, "GARANTIA 12 MESES:", "Sim", "150.00")]},
    ]})

    assert [(s["item_id"], s["servico"], s["preco"]) for s in _gravados(pedido)] == [
        (item_a, "Montagem", "80.00"), (item_b, "Garantia estendida", "150.00"),
    ]
    assert [_starhub(linha)["servicos"][0]["servico"] for linha in corpo["line_items"]] == [
        "Montagem", "Garantia estendida"]


def test_servico_recusado_tira_o_servico_do_item(api, pedido, produto):
    """EPOFW com "Não" no item diz que o servico saiu: nao pode ficar o "Sim" antigo."""
    criado = _put(api, pedido, {"line_items": [
        {"product_id": produto.pk, "meta_data": [_epofw(1, "MONTAGEM:", "Sim", "80")]},
    ]})
    item_a = criado["line_items"][0]["id"]
    corpo = _put(api, pedido, {"line_items": [
        {"id": item_a, "meta_data": [_epofw(1, "MONTAGEM:", "Não", "0")]}]})
    assert _gravados(pedido) is None
    assert corpo["line_items"][0]["meta_data"] == []


def test_servico_de_item_removido_sai_do_campo(api, pedido, produto):
    criado = _put(api, pedido, {"line_items": [
        {"product_id": produto.pk, "meta_data": [_epofw(1, "MONTAGEM:", "Sim", "80")]},
        {"product_id": produto.pk},
    ]})
    item_a = criado["line_items"][0]["id"]
    _put(api, pedido, {"line_items": [{"id": item_a, "quantity": 0}]})
    assert _gravados(pedido) is None


def test_starhub_que_nao_e_objeto_e_recusado(api, pedido):
    resposta = api.put(f"{URL}/{pedido.pk}", {"meta_data": [{"key": "starhub", "value": [1, 2]}]},
                       format="json")
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "rest_invalid_param"
