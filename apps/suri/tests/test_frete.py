"""Frete do hub no Suri Shop: orcamento do pedido em montagem."""

from decimal import Decimal

import pytest

from apps.logistica.models import FaixaCep, TabelaFrete
from apps.loja.models import Pedido
from apps.suri.frete import ligar_frete
from apps.suri.tests.loja_falsa import SuriFalso, configuracao, pedido
from apps.suri.webhooks import processar_webhook

pytestmark = pytest.mark.django_db
PEDIDOS = (("pedidos", "create"), ("pedidos", "update"))


def _tabela(nome, valor, prazo=0):
    tabela = TabelaFrete.objects.create(nome=nome, tipo=TabelaFrete.Tipo.FAIXA_CEP,
                                        prazo_dias=prazo, no_checkout=True)
    FaixaCep.objects.create(tabela=tabela, cep_inicial="60000000", cep_final="60999999",
                            valor=Decimal(valor))
    return tabela


def _montando(**extra):
    return pedido(status=0, logistic=None, **extra)


def _orcamentos(loja):
    return [c for m, r, c in loja.chamadas if r == "shop/orders/budget"]


def _processar(cfg):
    return processar_webhook(cfg, "51807", lambda *_: None)


def test_pedido_em_montagem_recebe_a_cotacao_mais_barata(conta, monkeypatch):
    loja = SuriFalso(pedidos=[_montando()]).instalar(monkeypatch)
    cfg = configuracao(conta, receber=PEDIDOS)
    ligar_frete(cfg, True)
    _tabela("Expressa", "25")
    economica = _tabela("Economica", "12.5", prazo=4)

    mensagem = _processar(cfg)

    corpo = _orcamentos(loja)[0]
    assert corpo["id"] == "51807" and corpo["logistic"]["name"] == "Economica"
    assert corpo["logistic"]["price"] == Decimal("12.50")
    assert corpo["logistic"]["providerId"] == f"HUB_{economica.pk}"
    assert corpo["logistic"]["shippingTimeEstimative"] == "4 dias uteis"
    assert corpo["items"][0]["Sku"] == "CAM-AZ"
    assert "Economica" in mensagem and not Pedido.objects.exists()


def test_mesmo_cep_e_itens_nao_manda_de_novo_mas_item_novo_manda(conta, monkeypatch):
    """Cada webhook do carrinho mandaria o mesmo orcamento de novo."""
    loja = SuriFalso(pedidos=[_montando()]).instalar(monkeypatch)
    cfg = configuracao(conta, receber=PEDIDOS)
    ligar_frete(cfg, True)
    _tabela("Expressa", "25")

    _processar(cfg)
    _processar(cfg)
    loja.pedidos_[0]["items"][0]["quantity"] = Decimal("3")
    _processar(cfg)

    assert len(_orcamentos(loja)) == 2


def test_frete_desligado_nao_responde_orcamento(conta, monkeypatch):
    loja = SuriFalso(pedidos=[_montando()]).instalar(monkeypatch)
    cfg = configuracao(conta, receber=PEDIDOS)
    _tabela("Expressa", "25")

    _processar(cfg)

    assert _orcamentos(loja) == []


def test_cep_sem_tabela_avisa_o_suri(conta, monkeypatch):
    comprador = {**pedido()["customer"], "address": {"zipCode": "90000-000"}}
    loja = SuriFalso(pedidos=[_montando(customer=comprador)]).instalar(monkeypatch)
    cfg = configuracao(conta, receber=PEDIDOS)
    ligar_frete(cfg, True)
    _tabela("Expressa", "25")

    mensagem = _processar(cfg)

    assert _orcamentos(loja)[0]["errorMessages"] == ["Nao entregamos no CEP 90000000."]
    assert "Sem frete" in mensagem
