from decimal import Decimal

import pytest

from apps.loja.models import Cliente, ItemPedido, MidiaProduto, Pedido
from apps.loja.services.variantes import criar_produto


@pytest.mark.django_db
def test_produto_na_listagem_junta_foto_nome_e_sku(admin_logado):
    """Produto precisa seguir o bloco visual do template, nao colunas de texto soltas."""
    produto = criar_produto("Tenis azul", sku="TEN-10", price=Decimal("89.90"))
    MidiaProduto.objects.create(
        produto=produto, url="https://cdn.test/tenis.jpg", alt_text="Tenis azul"
    )

    html = admin_logado.get("/admin/loja/produto/").content.decode()

    assert 'class="table-identity table-product"' in html
    assert 'src="https://cdn.test/tenis.jpg"' in html
    assert "Tenis azul" in html
    assert "SKU: TEN-10" in html


@pytest.mark.django_db
def test_pedido_na_listagem_mostra_avatar_dados_do_cliente_e_itens(admin_logado):
    """Pedido precisa identificar cliente e quantidade sem abrir a edicao."""
    cliente = Cliente.objects.create(
        email="ana@cliente.test",
        nome="Ana",
        sobrenome="Silva",
        avatar_url="https://cdn.test/ana.jpg",
    )
    pedido = Pedido.objects.create(cliente=cliente, total=Decimal("89.90"))
    ItemPedido.objects.create(pedido=pedido, nome="Tenis azul", sku="TEN-10")

    html = admin_logado.get("/admin/loja/pedido/").content.decode()

    assert 'class="table-identity table-customer"' in html
    assert 'src="https://cdn.test/ana.jpg"' in html
    assert "Ana Silva" in html
    assert "ana@cliente.test" in html
    assert "1 item" in html
