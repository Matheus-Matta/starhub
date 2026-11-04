"""Edicao dos itens do pedido no admin."""

import re
from decimal import Decimal

import pytest

from apps.loja.admin.pedidos_inlines import ItemPedidoForm
from apps.loja.models import Cliente, ItemPedido, Pedido
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db


@pytest.fixture
def pedido_com_item():
    produto = criar_produto("Balcao", sku="BAL-1", price=Decimal("100.00"))
    cliente = Cliente.objects.create(email="cliente@teste.local", nome="Cliente")
    pedido = Pedido.objects.create(cliente=cliente)
    ItemPedido.objects.create(
        pedido=pedido, variante=produto.variante_padrao,
        subtotal=Decimal("100.00"), total=Decimal("100.00"),
    )
    return pedido


def test_item_do_pedido_mostra_um_unico_seletor_de_produto(admin_logado, pedido_com_item):
    pedido = pedido_com_item
    html = admin_logado.get(f"/admin/loja/pedido/{pedido.pk}/change/").content.decode()
    inline = html.split('id="itens-group"', 1)[1].split('</fieldset>', 1)[0]

    assert 'name="itens-0-variante"' in inline
    assert 'name="itens-0-produto"' not in inline
    assert 'name="itens-0-nome"' not in inline
    assert re.search(r'class="column-variante[^>]*>Produto</th>', inline)


def test_trocar_variante_atualiza_produto_e_nome_automaticamente(pedido_com_item):
    pedido = pedido_com_item
    item = pedido.itens.get()
    nova_variante = criar_produto(
        "Mesa nova", sku="MESA-2", price=Decimal("125.00")).variante_padrao
    form = ItemPedidoForm(data={
        "variante": nova_variante.pk,
        "sku": nova_variante.sku,
        "quantidade": 2,
        "subtotal": "",
        "total": "",
    }, instance=item)

    assert form.is_valid(), form.errors
    salvo = form.save()

    assert salvo.produto == nova_variante.produto
    assert salvo.nome == "Mesa nova"
