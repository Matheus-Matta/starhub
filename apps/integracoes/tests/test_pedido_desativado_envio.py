"""Pedido desativado nao vai a marketplace nenhum, nem pela fila nem pelo Retomar."""

import pytest

from apps.core.origem import origem
from apps.loja.models import Pedido
from apps.loja.services.pedidos_ativos import mudar_ativo

from .envio_falso import MarketplaceFalso, ProdutoFalso, configuracao
from .test_envio_tarefa import _enviar

pytestmark = pytest.mark.django_db


class PedidoFalso(ProdutoFalso):
    recurso = "pedidos"
    modelo = Pedido


@pytest.fixture(autouse=True)
def _pedidos_no_falso(monkeypatch):
    monkeypatch.setattr(MarketplaceFalso, "recursos", (*MarketplaceFalso.recursos, PedidoFalso))


def _lojas():
    return configuracao("falso", recursos=("pedidos",)), configuracao(
        "shopify", recursos=("pedidos",))


def test_pedido_desativado_nao_entra_na_fila_de_nenhuma_loja(
        falsos, enfileirados, django_capture_on_commit_callbacks):
    """Sem o bloqueio, desativar (e cada edicao depois) mandava o pedido as lojas."""
    pedido = Pedido.objects.create(number="D1")
    _lojas()

    with django_capture_on_commit_callbacks(execute=True), origem("admin"):
        assert mudar_ativo(pedido.pk, False)
        pedido.refresh_from_db()
        pedido.notas = "editado depois de desativar"
        pedido.save()
        pedido.delete()

    assert enfileirados == []


def test_envio_que_ja_estava_na_fila_e_ignorado(falsos):
    """O pedido pode ser desativado com o envio esperando na fila (ou num Retomar)."""
    loja, _shopify = _lojas()
    pedido = Pedido.objects.create(number="D2", active=False)

    resultado = _enviar(loja, "pedidos", "update", pedido.pk)

    assert falsos == []
    assert "inativo" in resultado["message"]


def test_reativar_nao_reenvia_e_a_proxima_edicao_volta_a_enviar(
        falsos, enfileirados, django_capture_on_commit_callbacks):
    """Os webhooks foram ignorados enquanto desativado: reenviar sobrescreveria a loja."""
    pedido = Pedido.objects.create(number="D3", active=False)
    _lojas()

    with django_capture_on_commit_callbacks(execute=True), origem("admin"):
        assert mudar_ativo(pedido.pk, True)
    assert enfileirados == []

    with django_capture_on_commit_callbacks(execute=True), origem("admin"):
        pedido.refresh_from_db()
        pedido.notas = "voltou"
        pedido.save()
    assert sorted(enfileirados) == [("falso", "pedidos", "update", str(pedido.pk)),
                                    ("shopify", "pedidos", "update", str(pedido.pk))]
