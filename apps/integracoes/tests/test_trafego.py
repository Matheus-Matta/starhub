"""Tarefas mostram a requisicao recebida (webhook, API encaminhada) e a resposta dada."""

import json

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.integracoes import trafego
from apps.integracoes.models import ExecucaoIntegracao
from apps.woocommerce.tests import exemplos
from apps.woocommerce.tests.loja_falsa import LojaFalsa, configuracao
from apps.woocommerce.views import assinatura

pytestmark = pytest.mark.django_db


def test_credencial_nao_e_guardada_e_corpo_json_vira_objeto():
    request = RequestFactory().post(
        "/wp-json/wc/v3/orders/1?consumer_key=ck_x&status=a", data=b'{"status": "completed"}',
        content_type="application/json", HTTP_AUTHORIZATION="Basic segredo",
        HTTP_X_WC_WEBHOOK_TOPIC="order.updated")

    retrato = trafego.requisicao(request, request.body)

    assert retrato["corpo"] == {"status": "completed"}
    assert retrato["query"] == {"status": "a"}
    nomes = {nome.lower() for nome in retrato["cabecalhos"]}
    assert "authorization" not in nomes and "x-wc-webhook-topic" in nomes


def test_corpo_grande_e_cortado_com_aviso():
    guardado = trafego.corpo_guardavel("x" * (trafego.LIMITE + 10))

    assert guardado.endswith(trafego.CORTADO) and len(guardado) < trafego.LIMITE + 100


def test_webhook_do_woo_aparece_na_tarefa_com_corpo_e_resposta(
        admin_logado, conta, monkeypatch):
    LojaFalsa().instalar(monkeypatch)
    cfg = configuracao(conta, receber=(("produtos", "create"),))
    bruto = json.dumps(exemplos.produto_simples()).encode()
    admin_logado.post(reverse("woocommerce_webhook", args=[cfg.uuid, "produtos"]), bruto,
                      content_type="application/json", HTTP_X_WC_WEBHOOK_TOPIC="product.created",
                      HTTP_X_WC_WEBHOOK_SIGNATURE=assinatura("cs_teste", bruto))
    tarefa = ExecucaoIntegracao.objects.get()

    html = admin_logado.get(reverse("admin:integracoes_execucaointegracao_change",
                                    args=[tarefa.pk])).content.decode()

    assert "Requisicao recebida" in html and "POST /integracoes/woocommerce/webhook/" in html
    assert "product.created" in html and "Sofa Azul" in html
    assert "HTTP 202" in html


def test_tarefa_sem_trafego_nao_mostra_os_cards(admin_logado, conta):
    tarefa = ExecucaoIntegracao.objects.create(configuracao=configuracao(conta),
                                               tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR)

    html = admin_logado.get(reverse("admin:integracoes_execucaointegracao_change",
                                    args=[tarefa.pk])).content.decode()

    assert "Requisicao recebida" not in html and "tarefa-json" not in html
