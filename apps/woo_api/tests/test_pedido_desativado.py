"""Pedido desativado no hub: fora da lista do ERP; pelo id responde, mas nao muda."""

import pytest

from apps.loja.models import Pedido
from apps.woo_api.tests.conftest import criar_pedido

pytestmark = pytest.mark.django_db
URL = "/wp-json/wc/v3/orders"
V1 = "/wp-json/wc/v1/orders"


@pytest.fixture
def pedidos(conta):
    ativo, desativado = criar_pedido({}), criar_pedido({})
    Pedido.objects.filter(pk=desativado["id"]).update(active=False)
    return ativo["id"], desativado["id"]


@pytest.mark.parametrize("url", [URL, V1])
def test_lista_do_erp_nao_traz_o_pedido_desativado(api, pedidos, url):
    """Sem o filtro o ERP importava (e faturava) o pedido que o operador tirou do fluxo."""
    ativo, _desativado = pedidos
    resposta = api.get(url, {"status": "any"})
    assert [p["id"] for p in resposta.json()] == [ativo]
    assert resposta["X-WP-Total"] == "1"


@pytest.mark.parametrize("url", [URL, V1])
def test_get_e_put_do_pedido_desativado_respondem_sem_gravar(api, pedidos, url):
    """O ERP ja conhecia o pedido e mandava o cancelamento: o 404 virava erro no log
    dele a cada tentativa. Responde como esta e nao grava nada."""
    _ativo, desativado = pedidos
    antes = Pedido.objects.get(pk=desativado).updated_at

    lido = api.get(f"{url}/{desativado}")
    gravado = api.put(f"{url}/{desativado}", {"status": "cancelled", "customer_note": "x"},
                      format="json")

    assert (lido.status_code, gravado.status_code) == (200, 200)
    assert gravado.json()["status"] == "pending" and gravado.json()["customer_note"] == ""
    pedido = Pedido.objects.get(pk=desativado)
    assert (pedido.status, pedido.updated_at, pedido.active) == ("pending", antes, False)


def test_lote_do_erp_nao_altera_o_pedido_desativado(api, pedidos):
    ativo, desativado = pedidos
    resposta = api.post(f"{URL}/batch", {"update": [
        {"id": ativo, "status": "processing"}, {"id": desativado, "status": "processing"}]},
        format="json")
    ativo_saida, desativado_saida = resposta.json()["update"]
    assert (ativo_saida["status"], desativado_saida["status"]) == ("processing", "pending")
    assert Pedido.objects.get(pk=desativado).status == Pedido.Status.PENDENTE


def test_delete_do_pedido_desativado_nao_apaga(api, pedidos):
    _ativo, desativado = pedidos
    resposta = api.delete(f"{V1}/{desativado}?force=true")
    assert resposta.status_code in (200, 404)  # v1 aceita delete; v3 nem tem a rota
    assert Pedido.objects.filter(pk=desativado, status="pending").exists()
