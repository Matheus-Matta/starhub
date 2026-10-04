from decimal import Decimal

import pytest

from apps.loja.models import Categoria, Cliente, ItemPedido, MidiaProduto, Pedido
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


@pytest.mark.django_db
def test_cliente_na_listagem_mostra_avatar_nome_e_email(admin_logado):
    """A tabela de clientes precisa repetir a identificacao visual dos pedidos."""
    Cliente.objects.create(
        email="ana@cliente.test",
        nome="Ana",
        sobrenome="Silva",
        avatar_url="https://cdn.test/ana.jpg",
    )

    html = admin_logado.get("/admin/loja/cliente/").content.decode()

    assert 'class="table-identity table-customer"' in html
    assert 'class="table-customer-avatar" src="https://cdn.test/ana.jpg"' in html
    assert 'class="table-identity-title" title="Ana Silva">Ana Silva</span>' in html
    assert '<span class="table-identity-meta">ana@cliente.test</span>' in html


@pytest.mark.django_db
def test_categoria_na_listagem_mostra_imagem_nome_e_slug(admin_logado):
    """Categoria com imagem precisa usar a mesma celula visual dos produtos."""
    Categoria.objects.create(
        nome="Sala de jantar",
        slug="sala-de-jantar",
        imagem={"src": "https://cdn.test/sala.jpg", "alt": "Sala"},
    )

    html = admin_logado.get("/admin/loja/categoria/").content.decode()

    assert 'class="table-identity table-product"' in html
    assert 'src="https://cdn.test/sala.jpg"' in html
    assert 'title="Sala de jantar">Sala de jantar</span>' in html
    assert '<span class="table-identity-meta">Slug: sala-de-jantar</span>' in html


@pytest.mark.django_db
@pytest.mark.parametrize("situacao, texto, tom", [
    ("paid", "Pago", "success"),
    ("pending", "Pendente", "warning"),
    ("authorized", "Autorizado", "warning"),
    ("partially_paid", "Parcialmente pago", "warning"),
    ("refunded", "Reembolsado", "info"),
    ("partially_refunded", "Reembolso parcial", "info"),
    ("voided", "Estornado", "destructive"),
    ("failed", "Falhou", "destructive"),
])
def test_lista_de_pedidos_mostra_situacao_do_pagamento_em_badge(admin_logado, situacao, texto, tom):
    """Sem a coluna, o operador precisava abrir cada pedido para saber se foi pago."""
    Pedido.objects.create(financial_status=situacao, total=Decimal("10.00"))

    html = admin_logado.get("/admin/loja/pedido/").content.decode()

    assert f'<span class="badge badge-{tom}">{texto}</span>' in html
