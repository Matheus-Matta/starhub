"""Servico automatico entra no pedido que chega do Suri e da loja WooCommerce."""

from decimal import Decimal

import pytest

from apps.loja.models import Servico
from apps.loja.services.extras_pedido import extras
from apps.suri.importar_catalogo import importar_produto as importar_produto_suri
from apps.suri.importar_pedidos import importar_pedido as importar_pedido_suri
from apps.suri.tests.loja_falsa import pedido as pedido_suri
from apps.suri.tests.loja_falsa import produto as produto_suri
from apps.woocommerce.importar_pedidos import importar_pedido as importar_pedido_woo
from apps.woocommerce.importar_produtos import importar_produto as importar_produto_woo
from apps.woocommerce.tests import exemplos

pytestmark = pytest.mark.django_db


@pytest.fixture
def gratis():
    return Servico.objects.create(nome="Montagem gratis", sku="8875", preco=Decimal("0"),
                                  inclusao=Servico.Inclusao.TODOS)


def _do_servico(pedido, servico):
    return [s for s in extras(pedido).get("servicos", []) if s["servico_id"] == servico.pk]


def test_pedido_do_suri_ganha_o_servico_em_cada_item(gratis):
    importar_produto_suri(produto_suri())

    pedido, _ = importar_pedido_suri(pedido_suri())
    importar_pedido_suri(pedido_suri())

    pedido.refresh_from_db()
    assert [s["item_id"] for s in _do_servico(pedido, gratis)] == [pedido.itens.get().pk]
    assert pedido.total == Decimal("104.80"), "o total continua o que o cliente pagou"


def test_pedido_da_loja_woocommerce_ganha_o_servico(gratis):
    importar_produto_woo(exemplos.produto_simples())

    pedido, _ = importar_pedido_woo(exemplos.pedido(), "https://loja.test")

    pedido.refresh_from_db()
    assert {s["item_id"] for s in _do_servico(pedido, gratis)} == set(
        pedido.itens.values_list("pk", flat=True))
