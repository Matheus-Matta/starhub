"""Webhook da loja WooCommerce: assinatura, ping, cadastro e processamento."""

import json

import pytest
from django.urls import reverse

from apps.integracoes.models import ExecucaoIntegracao
from apps.loja.models import Produto
from apps.woocommerce.tests import exemplos
from apps.woocommerce.tests.loja_falsa import LojaFalsa, configuracao
from apps.woocommerce.views import assinatura
from apps.woocommerce.webhooks import processar_webhook
from apps.woocommerce.webhooks_cadastro import cadastrar_webhooks

pytestmark = pytest.mark.django_db
RECEBE_PRODUTOS = (("produtos", "create"), ("produtos", "update"), ("produtos", "delete"))


def _postar(client, cfg, corpo, topico="product.created", segredo="cs_teste", recurso="produtos"):
    bruto = json.dumps(corpo).encode()
    url = reverse("woocommerce_webhook", args=[cfg.uuid, recurso])
    return client.post(url, bruto, content_type="application/json",
                       HTTP_X_WC_WEBHOOK_TOPIC=topico,
                       HTTP_X_WC_WEBHOOK_SIGNATURE=assinatura(segredo, bruto))


def test_webhook_assinado_cria_a_tarefa_e_importa_o_produto(client, conta, monkeypatch):
    LojaFalsa().instalar(monkeypatch)
    cfg = configuracao(conta, receber=RECEBE_PRODUTOS)

    resposta = _postar(client, cfg, exemplos.produto_simples())

    assert resposta.status_code == 202
    execucao = ExecucaoIntegracao.objects.get()
    assert execucao.status == ExecucaoIntegracao.Status.CONCLUIDA
    assert execucao.parametros["reenvio"]["operacao"] == "create"
    assert Produto.objects.get().nome == "Sofa Azul"


def test_assinatura_errada_e_recusada(client, conta):
    cfg = configuracao(conta, receber=RECEBE_PRODUTOS)

    resposta = _postar(client, cfg, exemplos.produto_simples(), segredo="outro")

    assert resposta.status_code == 401 and not ExecucaoIntegracao.objects.exists()


def test_ping_do_cadastro_responde_200_sem_assinatura(client, conta):
    """Sem 200 no ping a loja recusa o webhook na hora de cadastrar."""
    cfg = configuracao(conta, receber=RECEBE_PRODUTOS)
    url = reverse("woocommerce_webhook", args=[cfg.uuid, "produtos"])

    resposta = client.post(url, {"webhook_id": "12"})

    assert resposta.status_code == 200 and not ExecucaoIntegracao.objects.exists()


def test_topico_de_outro_recurso_ou_desligado_e_ignorado(client, conta):
    cfg = configuracao(conta, receber=(("produtos", "create"),))

    trocado = _postar(client, cfg, {"id": 1}, topico="order.created")
    desligado = _postar(client, cfg, {"id": 1}, topico="product.deleted")

    assert (trocado.status_code, desligado.status_code) == (204, 204)


def test_update_de_registro_desconhecido_so_cria_com_criar_ligado(conta, monkeypatch):
    LojaFalsa().instalar(monkeypatch)
    so_update = configuracao(conta, receber=(("produtos", "update"),))

    mensagem = processar_webhook(so_update, "produtos", "update", exemplos.produto_simples(),
                                 lambda *_: None)

    assert "Receber > Criar" in mensagem and not Produto.objects.exists()


def test_delete_desativa_o_produto(conta, monkeypatch):
    LojaFalsa().instalar(monkeypatch)
    cfg = configuracao(conta, receber=RECEBE_PRODUTOS)
    processar_webhook(cfg, "produtos", "create", exemplos.produto_simples(), lambda *_: None)

    processar_webhook(cfg, "produtos", "delete", {"id": 15}, lambda *_: None)

    assert Produto.all_objects.get().active is False


def test_cadastro_troca_os_webhooks_do_hub_e_mantem_os_de_outros(conta, monkeypatch):
    cfg = configuracao(conta, receber=(("produtos", "update"), ("pedidos", "create")))
    nosso = f"https://hub.test/integracoes/woocommerce/webhook/{cfg.uuid}/produtos/"
    loja = LojaFalsa({"webhooks": [
        {"id": 1, "topic": "product.updated", "delivery_url": nosso},
        {"id": 2, "topic": "order.created", "delivery_url": "https://outro.app/hook"},
    ]}).instalar(monkeypatch)

    cadastrar_webhooks(cfg, lambda *_: None)

    apagados = [c[1] for c in loja.chamadas if c[0] == "DELETE"]
    criados = {c[2]["topic"]: c[2] for c in loja.chamadas if c[0] == "POST"}
    assert apagados == ["webhooks/1"]
    assert set(criados) == {"product.updated", "order.created"}
    assert criados["order.created"]["delivery_url"].endswith(f"/{cfg.uuid}/pedidos/")
    assert criados["order.created"]["secret"] == "cs_teste"
