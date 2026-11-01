"""Reimportar do Shopify: pedido gravado sem itens volta com os itens e o total da loja."""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.loja.models import Pedido
from apps.loja.services.variantes import criar_produto
from apps.shopify import pedidos_reimportar as reimportacao
from apps.shopify.cliente import ShopifyClient
from apps.shopify.contexto import coletando_avisos, usando_configuracao
from apps.shopify.tests.pedido_exemplo import produto_shopify_falso  # noqa: F401
from apps.shopify.tests.test_pedidos_graphql import NODE

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("produto_shopify_falso")]
GID = NODE["id"]


@pytest.fixture
def loja(monkeypatch):
    monkeypatch.setattr("apps.shopify.pedidos.completar_documento", lambda dados: dados)
    criar_produto("Poltrona Exemplo", sku="POLTRONA-001", price=Decimal("1999.89"))
    return ConfiguracaoIntegracao.objects.create(nome="Shopify", plataforma="shopify",
                                                 dominio_loja="loja.myshopify.com")


@pytest.fixture
def sem_itens(loja):
    """Como os pedidos 96-101: total da loja, nenhum item (o ERP soma R$ 0,00)."""
    pedido = Pedido.objects.create(origin="shopify", status="cancelled",
                                   total=Decimal("1889.79"))
    ExternalReference.objects.create(platform="shopify", entity_type="pedidos",
                                     external_id=GID, object_id=str(pedido.pk))
    return pedido


def _shopify(monkeypatch, nos):
    chamadas = []

    def graphql(self, query, variables=None):
        chamadas.append(variables)
        return {"nodes": nos}

    monkeypatch.setattr(ShopifyClient, "graphql", graphql)
    return chamadas


def _rodar(loja, pedidos):
    with usando_configuracao(loja), coletando_avisos() as avisos:
        return reimportacao.reimportar(loja, lambda *_: None, pedidos), avisos


def test_pedido_sem_itens_volta_com_os_itens_e_o_total_fecha(loja, sem_itens, monkeypatch):
    """O ERP recusava: "Total calculado R$ 0.00 difere do total do pedido"."""
    chamadas = _shopify(monkeypatch, [NODE])

    mensagem, avisos = _rodar(loja, [sem_itens.pk])

    sem_itens.refresh_from_db()
    item = sem_itens.itens.get()
    assert item.sku == "POLTRONA-001" and item.total == Decimal("1849.89")
    assert sem_itens.total == Decimal("1889.79") and Pedido.objects.count() == 1
    assert chamadas[0] == {"ids": [GID]}  # depois vem a consulta do cupom PROMO10
    assert "1 reimportado(s)" in mensagem and not avisos


def test_pedido_apagado_na_loja_avisa_e_fica_como_esta(loja, sem_itens, monkeypatch):
    _shopify(monkeypatch, [None])

    mensagem, avisos = _rodar(loja, [sem_itens.pk])

    assert not sem_itens.itens.exists()
    assert "1 nao existem mais" in mensagem and "nao existe mais" in avisos[0]["motivo"]


def test_consulta_usa_os_mesmos_campos_da_sincronizacao():
    assert "nodes(ids: $ids) { ... on Order {" in reimportacao.CONSULTA
    assert "lineItems(first: 50)" in reimportacao.CONSULTA
    assert reimportacao.CONSULTA.count("{") == reimportacao.CONSULTA.count("}")


def test_acao_da_lista_enfileira_so_os_do_shopify(admin_logado, sem_itens, monkeypatch):
    monkeypatch.setattr("apps.loja.admin.pedidos_cpf.colocar_na_fila", lambda *a: None)
    outro = Pedido.objects.create()

    admin_logado.post("/admin/loja/pedido/", {
        "action": "reimportar_do_shopify", "_selected_action": [sem_itens.pk, outro.pk]})

    execucao = ExecucaoIntegracao.objects.get(tipo="reimport_orders")
    assert execucao.parametros == {"pedidos": [sem_itens.pk]}
