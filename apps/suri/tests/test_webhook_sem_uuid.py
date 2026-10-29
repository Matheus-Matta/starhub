"""Webhook do Suri cadastrado so com a URL base (/integracoes/suri/webhook, sem uuid)."""

import json
import logging

import pytest
from django.test import override_settings

from apps.core.tenant.context import tenant_context
from apps.integracoes.models import ExecucaoIntegracao
from apps.suri.tests.loja_falsa import configuracao

pytestmark = pytest.mark.django_db
PEDIDOS = (("pedidos", "create"), ("pedidos", "update"))
MENSAGEM = {"id": "cb1:guid", "type": "message-received",
            "payload": {"user": {"Id": "u", "Phone": "5521999990000"}}}


@pytest.mark.parametrize("caminho", ["/integracoes/suri/webhook", "/integracoes/suri/webhook/"])
def test_url_base_com_uma_loja_suri_e_atendida_por_ela(client, conta, caminho, caplog):
    """O Portal do Suri tinha a URL sem uuid: 404 a cada 3 s, sem pista no log."""
    configuracao(conta, receber=PEDIDOS)

    with caplog.at_level(logging.INFO, logger="apps.suri.views"):
        resposta = client.post(caminho, json.dumps(MENSAGEM), content_type="application/json")

    assert resposta.status_code == 204
    assert not ExecucaoIntegracao.objects.exists()
    assert "evento do chatbot message-received ignorado" in caplog.text


@override_settings(LOG_CORPO_INTEGRACOES=True)
def test_evento_do_chatbot_gera_uma_linha_curta_sem_o_corpo(client, conta, caplog):
    """Cada mensagem do WhatsApp logava o corpo inteiro (telefone, conversa) e o aviso de
    URL sem uuid: o evento de pedido se perdia no meio do chat."""
    configuracao(conta, receber=PEDIDOS)

    with caplog.at_level(logging.INFO, logger="apps.suri.views"):
        client.post("/integracoes/suri/webhook", json.dumps(MENSAGEM),
                    content_type="application/json")

    assert len(caplog.records) == 1
    assert "5521999990000" not in caplog.text


def test_evento_que_nao_e_do_chatbot_avisa_o_endereco_certo(client, conta, caplog):
    cfg = configuracao(conta, receber=PEDIDOS)
    corpo = {"type": "order-status", "payload": {"Foo": 1}}

    with caplog.at_level(logging.INFO, logger="apps.suri.views"):
        resposta = client.post("/integracoes/suri/webhook", json.dumps(corpo),
                               content_type="application/json")

    assert resposta.status_code == 204
    assert f"/integracoes/suri/webhook/{cfg.uuid}/" in caplog.text
    assert "evento=order-status" in caplog.text
    assert '"Foo": "int"' in caplog.text


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
