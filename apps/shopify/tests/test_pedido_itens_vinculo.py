"""Id do line_item do Shopify no vinculo "itens_pedido", fora dos metadados do item.

Os metadados do ItemPedido saem no `meta_data` do line_item da API Woo: o id do
Shopify ali vazava dado de um marketplace para o ERP e misturava dado de loja no
registro do hub.
"""

import importlib
from decimal import Decimal

import pytest
from django.apps import apps

from apps.core.models import ExternalReference
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import ItemPedido, Pedido
from apps.loja.services.variantes import criar_produto
from apps.shopify.tests.pedido_exemplo import pedido_shopify, produto_shopify_falso  # noqa: F401
from apps.shopify.webhooks import processar_webhook

pytestmark = pytest.mark.usefixtures("produto_shopify_falso")
migracao = importlib.import_module("apps.shopify.migrations.0002_itens_pedido_no_vinculo")


def _webhook(operacao, dados):
    return processar_webhook(None, "pedidos", operacao, dados, lambda *_: None)


@pytest.fixture
def poltrona(db):
    ConfiguracaoIntegracao.objects.create(nome="Shopify", dominio_loja="loja.myshopify.com")
    return criar_produto("Poltrona Exemplo", sku="POLTRONA-001", price=Decimal("1499.90"))


def _chaves(item):
    lista = item.metadados if isinstance(item.metadados, list) else []
    return {meta.get("key") for meta in lista}


@pytest.mark.django_db
def test_item_importado_tem_vinculo_e_nao_guarda_o_id_nos_metadados(poltrona):
    _webhook("create", pedido_shopify())

    poltrona_item, almofada = Pedido.objects.get().itens.order_by("id")
    vinculos = dict(ExternalReference.objects.filter(entity_type="itens_pedido").values_list(
        "external_id", "object_id"))
    assert vinculos == {"gid://shopify/LineItem/555": str(poltrona_item.pk),
                        "gid://shopify/LineItem/556": str(almofada.pk)}
    assert "_shopify_line_item_id" not in _chaves(poltrona_item) | _chaves(almofada)


@pytest.mark.django_db
def test_orders_updated_acha_o_item_pelo_vinculo_e_nao_duplica(poltrona):
    """Sem casar pelo vinculo, cada orders/updated criaria os itens de novo."""
    _webhook("create", pedido_shopify())
    ids = list(ItemPedido.objects.order_by("id").values_list("pk", flat=True))

    _webhook("update", pedido_shopify(updated_at="2026-10-01T09:00:00-03:00"))

    assert list(ItemPedido.objects.order_by("id").values_list("pk", flat=True)) == ids


@pytest.mark.django_db
def test_migracao_move_o_id_para_o_vinculo_e_volta(poltrona):
    """Item importado antes da mudanca sem vinculo seria duplicado no proximo webhook."""
    _webhook("create", pedido_shopify())
    ExternalReference.objects.filter(entity_type="itens_pedido").delete()
    item = ItemPedido.objects.order_by("id").first()
    item.metadados = [{"id": 1, "key": "_shopify_line_item_id", "value": "555"},
                      {"id": 2, "key": "outro", "value": "x"}]
    item.save()

    migracao.mover_para_o_vinculo(apps, None)

    vinculo = ExternalReference.objects.get(entity_type="itens_pedido")
    assert (vinculo.external_id, vinculo.object_id) == ("gid://shopify/LineItem/555",
                                                        str(item.pk))
    item.refresh_from_db()
    assert item.metadados == [{"id": 2, "key": "outro", "value": "x"}]

    migracao.voltar_para_o_item(apps, None)

    item.refresh_from_db()
    assert {"key": "_shopify_line_item_id", "value": "555"}.items() <= next(
        m for m in item.metadados if m["key"] == "_shopify_line_item_id").items()
    assert not ExternalReference.objects.filter(entity_type="itens_pedido").exists()
