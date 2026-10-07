"""Servicos na API Woo: saem no line_item a que pertencem, nao no meta do pedido.

O armazenamento continua em pedido.metadados (starhub.servicos com item_id); so a
borda da API muda de lugar.
"""

from decimal import Decimal

import pytest

from apps.loja.models import Pedido, Servico
from apps.loja.services.extras_pedido import extras
from apps.loja.services.variantes import criar_produto

URL = "/wp-json/wc/v1/orders"
MONTAGEM = {"servico": "Montagem", "opcao": "Sim", "preco": "80.00"}


@pytest.fixture
def produto(db):
    return criar_produto("Poltrona Exemplo", sku="POLTRONA-001", price=Decimal("1499.90"))


@pytest.fixture
def pedido_com_servico(db, api, produto):
    """Pedido com dois itens e servico so no primeiro, gravado pelo formato antigo."""
    pedido = Pedido.objects.create(status="processing")
    criado = api.put(f"{URL}/{pedido.pk}", {
        "line_items": [{"product_id": produto.pk, "quantity": 1},
                       {"product_id": produto.pk, "quantity": 1}],
    }, format="json").json()
    item_a, item_b = (linha["id"] for linha in criado["line_items"])
    resposta = api.put(f"{URL}/{pedido.pk}", {"meta_data": [{"key": "starhub", "value": {
        "entrega": {"agendamento": "2026-10-15"},
        "servicos": [{"item_id": item_a, "sku": "POLTRONA-001", **MONTAGEM}],
    }}]}, format="json")
    assert resposta.status_code == 200, resposta.json()
    return pedido, item_a, item_b


def _meta(lista, chave="starhub"):
    return next((m["value"] for m in lista if m["key"] == chave), None)


def _saida(servico):
    """Como a API mostra o servico: id e SKU do cadastro, nome, preco e opcao."""
    cadastro = Servico.objects.get(nome=servico["servico"])
    return {"id": cadastro.pk, "nome": cadastro.nome, "sku": cadastro.sku,
            "preco": servico["preco"], "opcao": servico["opcao"]}


def _itens(corpo):
    return {linha["id"]: linha for linha in corpo["line_items"]}


def _put(api, pedido, corpo):
    resposta = api.put(f"{URL}/{pedido.pk}", corpo, format="json")
    assert resposta.status_code == 200, resposta.json()
    return resposta.json()


def test_get_mostra_o_servico_no_item_certo_e_nao_no_pedido(api, pedido_com_servico):
    """O ERP liga servico a produto: no pedido ele teria que caçar o item pelo item_id."""
    pedido, item_a, item_b = pedido_com_servico
    corpo = api.get(f"{URL}/{pedido.pk}").json()
    itens = _itens(corpo)

    assert _meta(corpo["meta_data"]) == {"entrega": {"agendamento": "15-10-2026"}}
    assert _meta(itens[item_a]["meta_data"]) == {"servicos": [_saida(MONTAGEM)]}
    assert _meta(itens[item_b]["meta_data"]) is None


def test_pedido_so_com_servicos_nao_manda_meta_starhub_vazio(api, pedido_com_servico):
    """Tirar servicos do pedido nao pode deixar um {"key": "starhub", "value": {}} sobrando."""
    pedido, item_a, _ = pedido_com_servico
    _put(api, pedido, {"meta_data": [{"key": "starhub", "value": {"entrega": {}}}]})
    corpo = api.get(f"{URL}/{pedido.pk}").json()
    assert _meta(corpo["meta_data"]) is None
    assert _meta(_itens(corpo)[item_a]["meta_data"]) == {"servicos": [_saida(MONTAGEM)]}


def test_round_trip_get_put_do_mesmo_corpo_nao_duplica_servicos(api, pedido_com_servico):
    """O ERP devolve o pedido como recebeu: os servicos nao podem dobrar nem mudar."""
    pedido, item_a, _ = pedido_com_servico
    antes = extras(Pedido.objects.get(pk=pedido.pk))["servicos"]
    corpo = api.get(f"{URL}/{pedido.pk}").json()

    depois = _put(api, pedido, {"meta_data": corpo["meta_data"],
                                "line_items": corpo["line_items"]})

    pedido.refresh_from_db()
    assert extras(pedido)["servicos"] == antes
    assert _meta(_itens(depois)[item_a]["meta_data"]) == {"servicos": [_saida(MONTAGEM)]}
    assert all(m["key"] != "starhub" for item in pedido.itens.all()
               for m in item.metadados or [])


def test_put_com_starhub_no_item_grava_o_servico_daquele_item(api, pedido_com_servico):
    pedido, item_a, item_b = pedido_com_servico
    garantia = {"servico": "Garantia estendida", "opcao": "12 meses", "preco": "150"}
    corpo = _put(api, pedido, {"line_items": [{"id": item_b, "meta_data": [
        {"key": "starhub", "value": {"servicos": [garantia]}}]}]})

    assert _meta(_itens(corpo)[item_b]["meta_data"]) == {
        "servicos": [_saida({**garantia, "preco": "150.00"})]}
    pedido.refresh_from_db()
    assert [(s["item_id"], s["sku"], s["servico"]) for s in extras(pedido)["servicos"]] == [
        (item_a, "POLTRONA-001", "Montagem"), (item_b, "POLTRONA-001", "Garantia estendida")]


def test_lista_vazia_no_starhub_do_item_remove_os_servicos_dele(api, pedido_com_servico):
    pedido, item_a, _ = pedido_com_servico
    corpo = _put(api, pedido, {"line_items": [{"id": item_a, "meta_data": [
        {"key": "starhub", "value": {"servicos": []}}]}]})

    assert _meta(_itens(corpo)[item_a]["meta_data"]) is None
    pedido.refresh_from_db()
    assert "servicos" not in extras(pedido)


def test_starhub_do_item_sem_lista_de_servicos_e_recusado(api, pedido_com_servico):
    pedido, item_a, _ = pedido_com_servico
    resposta = api.put(f"{URL}/{pedido.pk}", {"line_items": [{"id": item_a, "meta_data": [
        {"key": "starhub", "value": {"servicos": "Montagem"}}]}]}, format="json")
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "rest_invalid_param"
