"""Pedido desativado nao e alterado pelas lojas nem dispara StarChats ou aviso."""

from decimal import Decimal

import pytest

from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Pedido
from apps.loja.services.pedidos_ativos import AVISO_WEBHOOK, mudar_ativo
from apps.loja.services.variantes import criar_produto
from apps.shopify.tests.pedido_exemplo import pedido_shopify, produto_shopify_falso  # noqa: F401

pytestmark = pytest.mark.django_db


def _desativar(pedido):
    mudar_ativo(pedido.pk, False)
    pedido.refresh_from_db()
    return pedido


@pytest.mark.usefixtures("produto_shopify_falso")
def test_webhook_do_shopify_nao_mexe_no_pedido_desativado(monkeypatch):
    """O operador tirou o pedido do fluxo; o orders/updated seguinte o trazia de volta."""
    from apps.shopify.pedidos import importar_pedido
    from apps.shopify.webhooks import processar_webhook

    monkeypatch.setattr("apps.shopify.pedidos.completar_documento", lambda dados: dados)
    criar_produto("Poltrona Exemplo", sku="POLTRONA-001", price=Decimal("1499.90"))
    pedido = _desativar(importar_pedido(pedido_shopify())[0])

    mensagem = processar_webhook(
        ConfiguracaoIntegracao.objects.create(nome="Shopify", dominio_loja="loja.myshopify.com"),
        "pedidos", "update", pedido_shopify(note="mudou na loja", financial_status="refunded"),
        lambda *_: None)

    depois = Pedido.objects.get()
    assert mensagem == AVISO_WEBHOOK
    assert (depois.observacao_cliente, depois.financial_status, depois.active) == (
        pedido.observacao_cliente, pedido.financial_status, False)


def test_pedido_da_loja_woocommerce_desativado_fica_como_esta():
    from apps.woocommerce.importar_pedidos import importar_pedido
    from apps.woocommerce.importar_produtos import importar_produto
    from apps.woocommerce.tests import exemplos

    importar_produto(exemplos.produto_simples())
    _desativar(importar_pedido(exemplos.pedido())[0])

    pedido, criado = importar_pedido(exemplos.pedido(status="cancelled"))

    assert not criado and pedido.status == "processing" and Pedido.objects.count() == 1


def test_pedido_do_suri_desativado_fica_como_esta():
    from apps.suri.importar_catalogo import importar_produto
    from apps.suri.importar_pedidos import importar_pedido
    from apps.suri.tests.loja_falsa import pedido, produto

    importar_produto(produto())
    _desativar(importar_pedido(pedido())[0])

    obj, criado = importar_pedido(pedido(logistic={"name": "Entrega", "price": Decimal("10"),
                                                   "status": 4}))

    assert not criado and obj.status == "processing"


def test_pedido_desativado_nao_agenda_starchats_nem_aviso(monkeypatch):
    """Mensagem ao cliente sobre um pedido que o hub tirou do fluxo confunde o cliente."""
    mensagens, avisos = [], []
    monkeypatch.setattr("apps.starchats.sinais._agendar", lambda *args: mensagens.append(args))
    monkeypatch.setattr("apps.notificacoes.sinais._ligado", lambda *args: True)
    monkeypatch.setattr("apps.notificacoes.agenda.agendar", lambda *args: avisos.append(args))
    pedido = Pedido.objects.create(number="S1")
    mensagens.clear()
    avisos.clear()

    _desativar(pedido)
    pedido.notas = "editado"
    pedido.save()
    assert (mensagens, avisos) == ([], [])

    mudar_ativo(pedido.pk, True)
    assert mensagens == [], "a reativacao nao e novidade para o cliente"
    assert len(avisos) == 1, "a equipe ve o pedido alterado ao reativar"
