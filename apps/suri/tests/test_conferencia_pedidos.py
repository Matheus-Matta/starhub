"""Conferencia do beat no Suri: a API so filtra pela criacao, a janela e conferida aqui."""

import pytest

from apps.core.models import ExternalReference
from apps.core.tenant.context import tenant_context
from apps.loja.models import Pedido
from apps.suri.sincronizar import sincronizar_loja
from apps.suri.tests.loja_falsa import SuriFalso, configuracao, pedido

pytestmark = pytest.mark.django_db
JANELA = {"inicio": "2025-05-20T22:00:00+00:00", "fim": "2025-05-20T23:05:00+00:00",
          "conferido_ate": "2025-05-20T23:00:00+00:00"}


def test_conferencia_importa_o_pedido_criado_ou_alterado_na_janela(conta, monkeypatch):
    """Pagamento recebido na janela (pedido criado antes) tambem precisa ser atualizado."""
    pago_agora = pedido()  # criado 20:41, recebido 22:35: entra pelo recebimento
    antigo = pedido(id="51000", createdDate="2025-05-01T10:00:00Z",
                    receivedDate="2025-05-01T11:00:00Z",
                    finalizedDate="2025-05-01T12:00:00Z")
    SuriFalso(pedidos=[pago_agora, antigo]).instalar(monkeypatch)
    cfg = configuracao(conta, receber=(("pedidos", "get"),))

    with tenant_context(conta.pk):
        sincronizar_loja(cfg, lambda *_: None, recursos=["pedidos"], janela=JANELA)

    assert Pedido.objects.count() == 1
    assert list(ExternalReference.all_objects.filter(entity_type="pedidos").values_list(
        "external_id", flat=True)) == ["51807"]
