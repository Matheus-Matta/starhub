"""Pedido e cliente da loja WooCommerce no hub."""

from decimal import Decimal

import pytest

from apps.loja.models import Cliente, ItemPedido, Pedido
from apps.woocommerce.contexto import usando_configuracao
from apps.woocommerce.importar_clientes import importar_cliente
from apps.woocommerce.importar_pedidos import importar_pedido
from apps.woocommerce.importar_produtos import importar_produto
from apps.woocommerce.tests import exemplos
from apps.woocommerce.tests.loja_falsa import LojaFalsa, configuracao

pytestmark = pytest.mark.django_db


def test_cliente_entra_com_cpf_telefone_e_os_dois_enderecos():
    cliente, criado = importar_cliente(exemplos.cliente())

    assert criado and cliente.cpf == "52998224725" and cliente.telefone
    cobranca = cliente.vinculos_endereco.get(tipo="billing").endereco
    assert (cobranca.city, cobranca.number, cobranca.neighborhood) == ("Recife", "100", "Centro")
    assert cliente.vinculos_endereco.filter(tipo="shipping").exists()


def test_cpf_invalido_da_loja_nao_derruba_o_cliente():
    dados = exemplos.cliente()
    dados["billing"]["cpf"] = "111.111.111-11"

    cliente, _ = importar_cliente(dados)

    assert cliente.cpf == ""


def test_pedido_soma_os_valores_da_loja_em_decimal():
    importar_produto(exemplos.produto_simples())

    pedido, criado = importar_pedido(exemplos.pedido(), "https://loja.test")

    item = pedido.itens.get()
    assert criado and pedido.status == "processing" and pedido.financial_status == "paid"
    assert pedido.external_number == "501" and pedido.number != "501"
    assert (item.subtotal, item.total, item.total_desconto) == (
        Decimal("3599.80"), Decimal("3239.82"), Decimal("359.98"))
    assert item.variante.sku == "SOFA-1"
    assert (pedido.total_frete, pedido.total) == (Decimal("50.00"), Decimal("3289.82"))
    assert pedido.pagamentos.get().transaction_id == "TX-1"
    assert pedido.cliente.email == "ana@exemplo.test"
    assert pedido.endereco_entrega.city == "Recife"


def test_pedido_que_chega_de_novo_atualiza_status_e_itens_sem_duplicar():
    """order.updated repetia o pedido e os itens."""
    importar_produto(exemplos.produto_simples())
    importar_pedido(exemplos.pedido())

    pedido, criado = importar_pedido(exemplos.pedido(status="completed"))

    assert not criado and Pedido.objects.count() == 1 and ItemPedido.objects.count() == 1
    assert pedido.status == "completed" and pedido.fulfillment_status == "fulfilled"


def test_item_removido_na_loja_sai_do_pedido_do_hub():
    importar_produto(exemplos.produto_simples())
    importar_pedido(exemplos.pedido())

    pedido, _ = importar_pedido(exemplos.pedido(line_items=[]))

    assert not pedido.itens.exists() and pedido.total == Decimal("50.00")


def test_produto_que_o_hub_nao_tem_e_importado_da_loja(conta, monkeypatch):
    """Como no Shopify: o produto vem inteiro da loja, nunca um cadastro minimo."""
    LojaFalsa({"products": [exemplos.produto_simples()]}).instalar(monkeypatch)

    with usando_configuracao(configuracao(conta)):
        pedido, _ = importar_pedido(exemplos.pedido())

    assert pedido.itens.get().produto.nome == "Sofa Azul"


def test_cliente_do_pedido_e_o_mesmo_do_cadastro():
    importar_cliente(exemplos.cliente())

    importar_pedido(exemplos.pedido())

    assert Cliente.objects.count() == 1
