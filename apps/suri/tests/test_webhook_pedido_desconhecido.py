"""Evento do Suri que pode ser pedido, mas sem id que o hub reconheca: busca os pedidos.

A doc do Suri nao traz o corpo do webhook de pedido. Responder 204 a um formato novo
perdia o pedido em silencio; buscar os pedidos recentes pela API (o mesmo caminho do
Sincronizar loja > Pedidos) traz o pedido sem depender do formato.
"""

import json
import logging

import pytest

from apps.integracoes.models import ExecucaoIntegracao
from apps.suri.tests.loja_falsa import configuracao

pytestmark = pytest.mark.django_db
RECEBER = (("pedidos", "create"), ("pedidos", "update"), ("pedidos", "get"))


def _postar(client, cfg, corpo):
    return client.post(f"/integracoes/suri/webhook/{cfg.uuid}/", json.dumps(corpo),
                       content_type="application/json")


def _buscas():
    return list(ExecucaoIntegracao.objects.filter(
        tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR).values_list("parametros", flat=True))


def test_evento_sem_id_conhecido_busca_os_pedidos_recentes(client, conta, caplog):
    cfg = configuracao(conta, receber=RECEBER)

    with caplog.at_level(logging.INFO, logger="apps.suri"):
        resposta = _postar(client, cfg, {"type": "order-paid", "payload": {"Code": "X1"}})

    assert resposta.status_code == 202
    assert _buscas() == [{"direcao": "importar", "recursos": ["pedidos"]}]
    assert "buscando os pedidos recentes" in caplog.text


def test_mensagem_do_chat_com_pedido_busca_os_pedidos_recentes(client, conta):
    """Compra pelo catalogo do WhatsApp chega como mensagem com orderDetails."""
    cfg = configuracao(conta, receber=RECEBER)
    corpo = {"type": "message-received", "payload": {
        "user": {"Id": "u"}, "message": {"text": "", "orderDetails": {"items": [1]}}}}

    assert _postar(client, cfg, corpo).status_code == 202
    assert len(_buscas()) == 1


def test_conversa_comum_nao_busca_nada(client, conta):
    cfg = configuracao(conta, receber=RECEBER)
    corpo = {"type": "message-sent", "payload": {
        "user": {"Id": "u"}, "message": {"text": "oi", "orderDetails": None, "payment": None}}}

    assert _postar(client, cfg, corpo).status_code == 204
    assert _buscas() == []


def test_sem_buscar_pedidos_ligado_avisa_o_que_ligar(client, conta, caplog):
    cfg = configuracao(conta, receber=RECEBER[:2])

    with caplog.at_level(logging.INFO, logger="apps.suri"):
        resposta = _postar(client, cfg, {"type": "order-paid", "payload": {}})

    assert resposta.status_code == 204
    assert _buscas() == []
    assert "Receber > Pedidos > Buscar" in caplog.text


def test_busca_ja_na_fila_nao_cria_outra(client, conta):
    """Varios eventos seguidos viram uma busca so: a da fila ja traz todos."""
    cfg = configuracao(conta, receber=RECEBER)

    for _ in range(3):
        assert _postar(client, cfg, {"type": "order-paid", "payload": {}}).status_code == 202
    assert len(_buscas()) == 1
