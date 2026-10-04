import logging
from datetime import datetime

import pytest
from django.utils import timezone

from apps.loja.models import Pedido
from apps.loja.services.variantes import criar_produto
from apps.woo_api.tests.conftest import criar_pedido

URL = "/wp-json/wc/v3/orders"
URL_DO_LOG = (
    "/wp-json/wc/v3/orders/?page=1&per_page=10&modified_after=2026-09-23T00:00:00"
    "&status=pending,processing,completed,cancelled"
)


@pytest.fixture
def produto(db):
    return criar_produto("Caneca", sku="CAN-1", price="10.00")


def _alterado_em(pedido, ano, mes, dia):
    # updated_at e auto_now: so o update() do queryset permite fixar a data no teste.
    momento = timezone.make_aware(datetime(ano, mes, dia, 12))
    Pedido.objects.filter(pk=pedido.pk).update(updated_at=momento)


def test_v3_lista_pedidos_com_a_url_exata_do_erp(api, produto):
    """O ERP recebia 404 em wc/v3/orders; agora filtra por status e data de alteracao."""
    antigo = Pedido.objects.create(status="processing")
    recente = Pedido.objects.create(status="completed")
    em_espera = Pedido.objects.create(status="on-hold")
    fora_do_filtro = Pedido.objects.create(status="refunded")
    _alterado_em(antigo, 2026, 9, 1)
    for pedido in (recente, em_espera, fora_do_filtro):
        _alterado_em(pedido, 2026, 9, 28)

    resposta = api.get(URL_DO_LOG)

    assert resposta.status_code == 200
    assert [p["id"] for p in resposta.json()] == [recente.pk]
    assert resposta["X-WP-Total"] == "1"
    assert resposta["X-WP-TotalPages"] == "1"


def test_v3_modified_before_exclui_os_pedidos_recentes(api):
    """Sem o filtro por data pela v3, o ERP releria todos os pedidos a cada ciclo."""
    antigo = Pedido.objects.create(status="pending")
    recente = Pedido.objects.create(status="pending")
    _alterado_em(antigo, 2026, 9, 1)
    _alterado_em(recente, 2026, 9, 28)

    resposta = api.get(f"{URL}?modified_before=2026-09-10T00:00:00")

    assert [p["id"] for p in resposta.json()] == [antigo.pk]


V1 = "/wp-json/wc/v1/orders"


@pytest.mark.parametrize("url", [URL, V1])
def test_post_de_pedido_e_recusado_com_rest_no_route_e_nada_e_criado(api, produto, url):
    """Pedido so nasce vindo de marketplace: o ERP nao pode criar pela API Woo."""
    resposta = api.post(
        url, {"line_items": [{"product_id": produto.pk, "quantity": 2}]}, format="json"
    )
    assert resposta.status_code == 404
    assert resposta.json()["code"] == "rest_no_route"
    assert not Pedido.objects.exists()


@pytest.mark.parametrize("url", [URL, V1])
def test_delete_de_pedido_e_recusado_e_o_pedido_continua(api, url):
    pedido = criar_pedido({})
    resposta = api.delete(f"{url}/{pedido['id']}?force=true")
    assert resposta.status_code == 404
    assert resposta.json()["code"] == "rest_no_route"
    assert Pedido.objects.filter(pk=pedido["id"]).exists()


@pytest.mark.parametrize("url", [URL, V1])
def test_le_e_atualiza_pedido_por_put_patch_e_post(api, produto, url, caplog):
    pedido = criar_pedido({"line_items": [{"product_id": produto.pk, "quantity": 2}]})
    pk = pedido["id"]
    assert pedido["total"] == "20.00"

    assert api.get(f"{url}/{pk}").json()["id"] == pk
    with caplog.at_level(logging.INFO, logger="django.request"):
        resposta = api.put(f"{url}/{pk}", {"status": "completed"}, format="json")
    assert resposta.json()["status"] == "completed"
    assert "Woo recebeu atualizacao do pedido" in caplog.text
    assert api.patch(f"{url}/{pk}", {"status": "on-hold"}, format="json").status_code == 200
    assert api.post(f"{url}/{pk}", {"status": "processing"}, format="json").json()[
        "status"
    ] == "processing"
    assert Pedido.objects.count() == 1


@pytest.mark.parametrize("url", [f"{URL}/batch", f"{V1}/batch"])
@pytest.mark.parametrize("operacao", [
    {"create": [{"status": "pending"}]},
    {"delete": [1]},
])
def test_lote_de_pedidos_recusa_create_e_delete(api, url, operacao):
    existente = criar_pedido({})
    corpo = {**operacao, "update": [{"id": existente["id"], "status": "completed"}]}
    if "delete" in operacao:
        corpo["delete"] = [existente["id"]]

    resposta = api.post(url, corpo, format="json")

    assert resposta.status_code == 404
    assert resposta.json()["code"] == "rest_no_route"
    pedidos = Pedido.objects.all()
    assert [(p.pk, p.status) for p in pedidos] == [(existente["id"], "pending")]


@pytest.mark.parametrize("url", [f"{URL}/batch", f"{V1}/batch"])
def test_lote_de_pedidos_atualiza(api, url):
    existente = criar_pedido({})

    resposta = api.post(
        url, {"update": [{"id": existente["id"], "status": "processing"}]}, format="json"
    )

    assert resposta.status_code == 200
    assert resposta.json()["update"][0]["status"] == "processing"


def test_v3_consulta_nao_registra_credenciais(api, caplog):
    with caplog.at_level(logging.INFO, logger="django.request"):
        api.get(f"{URL}?consumer_key=ck_x&consumer_secret=cs_y&status=any")
    assert "Woo consultou pedidos" in caplog.text
    assert "cs_y" not in caplog.text
