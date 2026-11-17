"""Webhook de variacao da loja WooCommerce: muda a variacao, nunca a variante padrao.

Alterar uma variacao no Woo dispara product.updated com o corpo DA VARIACAO
(type "variation", parent_id do pai). O hub achava o pai pelo SKU e gravava o preco e
o estoque da variacao na variante padrao, e ainda vinculava o id da variacao ao pai.
"""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Produto, VarianteProduto
from apps.woocommerce.tests import exemplos
from apps.woocommerce.tests.loja_falsa import LojaFalsa, configuracao
from apps.woocommerce.webhooks import processar_webhook

pytestmark = pytest.mark.django_db
RECEBE = (("produtos", "create"), ("produtos", "update"))


def _corpo_variacao(**extra):
    return {**exemplos.variacao(22, "Azul", "CAM-AZ", "89.90", 2), "type": "variation",
            "parent_id": 20, "name": "Camiseta - Azul", **extra}


@pytest.fixture
def loja(monkeypatch):
    return LojaFalsa({
        "products": [exemplos.produto_variavel()],
        "products/20/variations": [exemplos.variacao(21, "Preta", "CAM-PR", "79.90", 5),
                                   exemplos.variacao(22, "Azul", "CAM-AZ", "79.90", 6)],
    }).instalar(monkeypatch)


@pytest.fixture
def camiseta(conta, loja):
    cfg = configuracao(conta, receber=RECEBE)
    processar_webhook(cfg, "produtos", "create", exemplos.produto_variavel(), lambda *_: None)
    return cfg


def _estoques():
    return dict(VarianteProduto.objects.values_list("sku", "inventory_quantity"))


def test_update_da_variacao_muda_a_variacao_e_nao_a_padrao(conta, camiseta):
    processar_webhook(camiseta, "produtos", "update", _corpo_variacao(), lambda *_: None)

    assert _estoques() == {"CAM-PR": 5, "CAM-AZ": 2}
    azul = VarianteProduto.objects.get(sku="CAM-AZ")
    assert azul.price == Decimal("89.90") and Produto.objects.count() == 1
    # O id da variacao nunca vira vinculo de produto.
    assert not ExternalReference.objects.filter(entity_type="produtos", external_id="22")


def test_variacao_pelo_sku_mesmo_sem_vinculo(conta, camiseta):
    """SKU primeiro: o vinculo da variacao pode faltar (produto cadastrado no hub)."""
    ExternalReference.objects.filter(entity_type="variantes").delete()

    processar_webhook(camiseta, "produtos", "update", _corpo_variacao(), lambda *_: None)

    assert _estoques() == {"CAM-PR": 5, "CAM-AZ": 2}


def test_variacao_nova_entra_no_produto_pai(conta, camiseta, loja):
    nova = exemplos.variacao(23, "Verde", "CAM-VE", "79.90", 4)
    loja.colecoes["products/20/variations"].append(nova)
    loja.colecoes["products"][0]["variations"].append(23)

    processar_webhook(camiseta, "produtos", "update", {**nova, "type": "variation",
                                                       "parent_id": 20}, lambda *_: None)

    assert _estoques() == {"CAM-PR": 5, "CAM-AZ": 6, "CAM-VE": 4}
    assert Produto.objects.count() == 1
