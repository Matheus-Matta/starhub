"""Pedido de outra loja criado no WooCommerce no formato legado (pedido-completo.json)."""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.core.origem import origem
from apps.loja.models import ItemPedido, Pedido, Servico
from apps.loja.services.extras_pedido import mesclar_extras
from apps.loja.services.variantes import criar_produto
from apps.loja.totais import recalcular_totais
from apps.woocommerce.envio.marketplace import WooCommerceMarketplace
from apps.woocommerce.importar_pedidos import importar_pedido
from apps.woocommerce.tests.loja_falsa import LojaFalsa, configuracao

pytestmark = pytest.mark.django_db


@pytest.fixture
def pedido_shopify():
    """Pedido vindo da Shopify com Montagem (R$ 80) ja somada no item do sofa."""
    sofa = criar_produto("Sofa", sku="SOF-1", price=Decimal("1500.00"))
    ExternalReference.objects.create(platform="woocommerce", entity_type="produtos",
                                     external_id="20", object_id=str(sofa.pk))
    montagem = Servico.objects.create(nome="Montagem", sku="SERV-MONT")
    with origem("shopify"):
        pedido = Pedido.objects.create(status="processing", source_name="shopify")
        item = ItemPedido.objects.create(
            pedido=pedido, produto=sofa, variante=sofa.variante_padrao, nome="Sofa",
            sku="SOF-1", quantidade=1, preco_unitario=Decimal("1500.00"),
            subtotal=Decimal("1580.00"), total=Decimal("1580.00"))
        mesclar_extras(pedido, {
            "origem": {"canal": "shopify", "id": "123"},
            "entrega": {"agendamento": "2026-10-30"},
            "servicos": [{"item_id": item.pk, "sku": "SOF-1", "servico": "Montagem",
                          "servico_id": montagem.pk, "opcao": "Sim", "preco": "80.00",
                          "somado": True}]})
        pedido.save()
        recalcular_totais(pedido)
    return pedido


def _enviar(conta, monkeypatch, pedido, legado=True):
    loja = LojaFalsa().instalar(monkeypatch)
    cfg = configuracao(conta, enviar=[("pedidos", "update")], pedido_legado=legado)
    return WooCommerceMarketplace(cfg).enviar("pedidos", "create", pedido.pk), loja


def test_pedido_vai_com_o_servico_no_meta_e_fora_do_valor(conta, monkeypatch, pedido_shopify):
    """Como o pedido-completo.json: o ERP le o servico no meta e soma sozinho; com o
    valor no item ele cobraria a Montagem duas vezes."""
    mensagem, loja = _enviar(conta, monkeypatch, pedido_shopify)

    _, rota, corpo = loja.chamadas[-1]
    item = corpo["line_items"][0]
    assert rota == "orders" and mensagem.startswith("criado")
    assert (item["product_id"], item["subtotal"], item["total"]) == (20, "1500.00", "1500.00")
    meta_item = {m["key"]: m["value"] for m in item["meta_data"]}
    assert meta_item["starhub"]["servicos"][0]["preco"] == "80.00"
    assert "epofw_field_1" in meta_item
    meta = {m["key"]: m["value"] for m in corpo["meta_data"]}
    assert meta["starhub"]["entrega"]["agendamento"] == "30-10-2026"
    assert meta["starhub_pedido"] == str(pedido_shopify.uuid)
    assert corpo["status"] == "processing" and "coupon_lines" not in corpo
    assert ExternalReference.objects.filter(platform="woocommerce",
                                            entity_type="pedidos").exists()


def test_sem_o_switch_o_pedido_nao_e_criado_na_loja(conta, monkeypatch, pedido_shopify):
    mensagem, loja = _enviar(conta, monkeypatch, pedido_shopify, legado=False)

    assert mensagem.startswith("ignorado") and not loja.chamadas


def test_pedido_novo_de_outra_loja_agenda_a_criacao_so_com_o_switch(
        conta, monkeypatch, django_capture_on_commit_callbacks):
    agendados = []
    monkeypatch.setattr("apps.integracoes.envio.distribuidor._enfileirar",
                        lambda *args: agendados.append(args))
    ligada = configuracao(conta, pedido_legado=True)

    with django_capture_on_commit_callbacks(execute=True), origem("shopify"):
        pedido = Pedido.objects.create(status="processing")

    assert (str(ligada.pk), "pedidos", "create", str(pedido.pk)) in agendados
    ligada.pedido_legado = False
    ligada.save()
    agendados.clear()
    with django_capture_on_commit_callbacks(execute=True), origem("shopify"):
        Pedido.objects.create(status="processing")
    assert not agendados


def test_eco_do_webhook_do_woo_nao_duplica_nem_muda_o_pedido(conta, pedido_shopify):
    """O pedido criado pelo hub volta pelo order.created: a loja nao manda nele."""
    total = pedido_shopify.total

    obj, criado = importar_pedido({"id": 900, "status": "completed", "total": "1.00",
                                   "meta_data": [{"key": "starhub_pedido",
                                                  "value": str(pedido_shopify.uuid)}]})

    assert obj == pedido_shopify and not criado and Pedido.objects.count() == 1
    pedido_shopify.refresh_from_db()
    assert pedido_shopify.total == total and pedido_shopify.status == "processing"
