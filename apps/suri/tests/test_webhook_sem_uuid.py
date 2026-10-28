"""Webhook do Suri cadastrado so com a URL base (/integracoes/suri/webhook, sem uuid)."""

import json
import logging

import pytest

from apps.core.tenant.context import tenant_context
from apps.integracoes.models import ExecucaoIntegracao
from apps.suri.tests.loja_falsa import configuracao

pytestmark = pytest.mark.django_db
PEDIDOS = (("pedidos", "create"), ("pedidos", "update"))
MENSAGEM = {"id": "cb1:guid", "type": "message-received", "payload": {"user": {"Id": "u"}}}


@pytest.mark.parametrize("caminho", ["/integracoes/suri/webhook", "/integracoes/suri/webhook/"])
def test_url_base_com_uma_loja_suri_e_atendida_por_ela(client, conta, caminho, caplog):
    """O Portal do Suri tinha a URL sem uuid: 404 a cada 3 s, sem pista no log."""
    cfg = configuracao(conta, receber=PEDIDOS)

    with caplog.at_level(logging.INFO, logger="apps.suri.views"):
        resposta = client.post(caminho, json.dumps(MENSAGEM), content_type="application/json")

    assert resposta.status_code == 204
    assert not ExecucaoIntegracao.objects.exists()
    assert f"/integracoes/suri/webhook/{cfg.uuid}/" in caplog.text
    assert "evento=message-received" in caplog.text


def test_url_base_com_duas_lojas_suri_continua_404(client, conta, outra_conta, caplog):
    """Com duas contas no Suri, adivinhar a loja mandaria o pedido para a conta errada."""
    configuracao(conta, receber=PEDIDOS)
    with tenant_context(outra_conta):
        configuracao(outra_conta, receber=PEDIDOS)

    with caplog.at_level(logging.INFO, logger="apps.suri.views"):
        resposta = client.post("/integracoes/suri/webhook", json.dumps(MENSAGEM),
                               content_type="application/json")

    assert resposta.status_code == 404
    assert "2 lojas Suri ativas" in caplog.text
