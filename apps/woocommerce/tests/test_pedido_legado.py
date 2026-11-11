"""Pedido de outra loja criado no WooCommerce: criar e da matriz, o switch e o formato."""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.core.origem import origem
from apps.loja.models import ItemPedido, Pedido, Servico
from apps.loja.services.extras_pedido import extras, mesclar_extras
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
    cfg = configuracao(conta, enviar=[("pedidos", "create"), ("pedidos", "update")],
                       pedido_legado=legado)
    return WooCommerceMarketplace(cfg).enviar("pedidos", "create", pedido.pk), loja


def _item(loja):
    corpo = loja.chamadas[-1][2]
    return corpo, corpo["line_items"][0]


def test_formato_legado_leva_o_servico_como_taxa_fora_do_preco_do_produto(
        conta, monkeypatch, pedido_shopify):
    """Switch ligado: o Woo soma o total pelas linhas. Servico so no meta ficava fora do
    total (1500); dentro do item e tambem no EPOFW, o ERP contava duas vezes (1660)."""
    mensagem, loja = _enviar(conta, monkeypatch, pedido_shopify, legado=True)

    corpo, item = _item(loja)
    assert loja.chamadas[-1][1] == "orders" and mensagem.startswith("criado")
    assert (item["product_id"], item["subtotal"], item["total"]) == (20, "1500.00", "1500.00")
    assert corpo["fee_lines"] == [
        {"name": "Montagem (Sofa)", "total": "80.00", "tax_status": "none"}]
    meta_item = {m["key"]: m["value"] for m in item["meta_data"]}
    assert meta_item["starhub"]["servicos"][0]["preco"] == "80.00"
    assert not any(chave.startswith("epofw_field_") for chave in meta_item)
    meta = {m["key"]: m["value"] for m in corpo["meta_data"]}
    assert meta["starhub"]["entrega"]["agendamento"] == "30-10-2026"
    assert meta["starhub_pedido"] == str(pedido_shopify.uuid)
    assert corpo["status"] == "processing" and "coupon_lines" not in corpo
    assert ExternalReference.objects.filter(platform="woocommerce",
                                            entity_type="pedidos").exists()


def test_servico_so_informado_pela_loja_nao_vira_taxa(conta, monkeypatch, pedido_shopify):
    """Garantia sem "somado": o cliente nao pagou por ela, a taxa aumentaria o total."""
    garantia = {"item_id": pedido_shopify.itens.get().pk, "sku": "SOF-1",
                "servico": "Garantia", "opcao": "Sim", "preco": "50.00"}
    mesclar_extras(pedido_shopify, {"servicos": extras(pedido_shopify)["servicos"] + [garantia]})
    pedido_shopify.save()

    _, loja = _enviar(conta, monkeypatch, pedido_shopify, legado=True)

    assert [taxa["name"] for taxa in loja.chamadas[-1][2]["fee_lines"]] == ["Montagem (Sofa)"]


def test_formato_padrao_manda_o_valor_do_servico_somado_no_item(
        conta, monkeypatch, pedido_shopify):
    """Switch desligado: o pedido vai como o hub guarda, com a Montagem dentro do item."""
    _, loja = _enviar(conta, monkeypatch, pedido_shopify, legado=False)

    _, item = _item(loja)
    assert (item["subtotal"], item["total"]) == ("1580.00", "1580.00")
    meta_item = {m["key"]: m["value"] for m in item["meta_data"]}
    assert meta_item["starhub"]["servicos"][0]["nome"] == "Montagem"
    # O ERP soma o epofw_price no item: com a Montagem ja dentro, cobraria duas vezes.
    assert not any(chave.startswith("epofw_field_") for chave in meta_item)


def test_criar_pedido_depende_so_da_matriz_e_nao_do_switch(conta, monkeypatch, pedido_shopify):
    """Enviar > Pedidos > Criar desligado: nada vai, mesmo com o formato legado ligado."""
    loja = LojaFalsa().instalar(monkeypatch)
    cfg = configuracao(conta, enviar=[("pedidos", "update")], pedido_legado=True)

    mensagem = WooCommerceMarketplace(cfg).enviar("pedidos", "update", pedido_shopify.pk)

    assert mensagem.startswith("ignorado") and "'criar' esta desligado" in mensagem
    assert not loja.chamadas


def test_pedido_novo_de_outra_loja_agenda_a_criacao_so_com_a_matriz(
        conta, monkeypatch, django_capture_on_commit_callbacks):
    agendados = []
    monkeypatch.setattr("apps.integracoes.envio.distribuidor._enfileirar",
                        lambda *args: agendados.append(args))
    ligada = configuracao(conta, enviar=[("pedidos", "create")])

    with django_capture_on_commit_callbacks(execute=True), origem("shopify"):
        pedido = Pedido.objects.create(status="processing")

    assert (str(ligada.pk), "pedidos", "create", str(pedido.pk)) in agendados
    ligada.permissoes["enviar"]["pedidos"]["create"] = False
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
