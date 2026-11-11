"""Preco do item do pedido: preenchido sozinho ao criar e travado depois de gravado.

O preco do item e o que o cliente pagou: mudado na tela, o pedido deixa de bater com
a loja e com o ERP.
"""

from decimal import Decimal

import pytest

from apps.loja.admin.pedidos_inlines import ItemPedidoForm
from apps.loja.models import Cliente, ItemPedido, Pedido
from apps.loja.services.variantes import criar_produto
from apps.loja.tests.test_servicos_pedido_admin import _Campos
from apps.loja.tests.test_servicos_pedido_tela import criar_pedido_com_servicos

pytestmark = pytest.mark.django_db

PRECO = ["subtotal", "total"]


@pytest.fixture
def pedido(conta):
    produto = criar_produto("Balcao", sku="BAL-1", price=Decimal("100.00"))
    cliente = Cliente.objects.create(email="cliente@teste.local", nome="Cliente")
    pedido = Pedido.objects.create(cliente=cliente)
    ItemPedido.objects.create(
        pedido=pedido, variante=produto.variante_padrao, produto=produto, nome="Balcao",
        sku="BAL-1", subtotal=Decimal("90.00"), total=Decimal("90.00"),
    )
    return pedido


def test_item_ja_gravado_trava_so_o_preco(pedido):
    form = ItemPedidoForm(instance=pedido.itens.get())

    assert [n for n in PRECO if form.fields[n].disabled] == PRECO
    assert not form.fields["variante"].disabled and not form.fields["quantidade"].disabled


def test_item_novo_tem_o_preco_preenchido_sozinho():
    form = ItemPedidoForm()

    assert not any(form.fields[n].disabled for n in PRECO)
    assert form.fields["total"].widget.attrs["placeholder"] == "Automatico"


def test_preco_do_item_mandado_na_mao_nao_muda_o_item(admin_logado, pedido):
    """O navegador nao manda campo desabilitado, mas um POST montado na mao manda."""
    url = f"/admin/loja/pedido/{pedido.pk}/change/"
    campos = _Campos()
    campos.feed(admin_logado.get(url).content.decode())

    resposta = admin_logado.post(url, {**campos.dados, "itens-0-total": "1.00",
                                       "itens-0-subtotal": "1.00"})

    assert resposta.status_code == 302
    assert pedido.itens.get().total == Decimal("90.00")


def _mudar_quantidade(item, quantidade):
    form = ItemPedidoForm(instance=item, data={
        "variante": item.variante_id, "quantidade": quantidade})
    assert form.is_valid(), form.errors
    return form.save()


def test_mudar_quantidade_recalcula_pelo_preco_que_o_cliente_pagou(pedido):
    """O produto custa 100 hoje, mas o cliente pagou 90: 3 unidades sao 270, nao 300."""
    item = _mudar_quantidade(pedido.itens.get(), 3)

    assert (item.quantidade, item.subtotal, item.total) == (3, Decimal("270.00"),
                                                            Decimal("270.00"))


def test_mudar_quantidade_nao_multiplica_o_servico_somado_no_item(conta):
    """Sofa 1500 + Montagem 80 somada: 2 sofas sao 3080; a Montagem continua uma so."""
    _, sofa, *_ = criar_pedido_com_servicos()
    sofa.variante = sofa.produto.variante_padrao
    sofa.save()

    item = _mudar_quantidade(sofa, 2)

    assert item.total == Decimal("3080.00")
