from decimal import Decimal

import pytest

from apps.core.models import ExternalReference, Origin
from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Produto, TipoVariante, VarianteProduto
from apps.shopify.webhooks import processar_webhook


def _configuracao(conta):
    matriz = permissoes.matriz_vazia()
    matriz["receber"]["produtos"]["create"] = True
    return ConfiguracaoIntegracao.objects.create(
        account=conta, plataforma="shopify", permissoes=matriz
    )


def _dados():
    return {
        "id": 10,
        "title": "Sofa Shopify",
        "handle": "sofa-shopify",
        "vendor": "Moveis FDC",
        "body_html": "<p>Sofa confortavel</p>",
        "options": [{"name": "Cor", "position": 1, "values": ["Bege", "Prata"]}],
        "variants": [
            {
                "id": 101,
                "title": "Bege",
                "sku": "SOFA-BEGE",
                "barcode": "7891234567895",
                "price": "1800.00",
                "compare_at_price": "2000.00",
                "inventory_quantity": 3,
                "inventory_policy": "deny",
                "position": 1,
                "option1": "Bege",
            },
            {
                "id": 102,
                "title": "Prata",
                "sku": "SOFA-PRATA",
                "price": "1999.99",
                "compare_at_price": None,
                "inventory_quantity": 14,
                "inventory_policy": "continue",
                "position": 2,
                "option1": "Prata",
            },
        ],
    }


@pytest.mark.django_db
def test_produto_shopify_criado_adapta_variantes_opcoes_precos_e_estoque(conta):
    """Create de produto variavel precisa virar o modelo canonico completo do StarHub."""
    processar_webhook(
        _configuracao(conta), "produtos", "create", _dados(), lambda *_: None
    )

    produto = Produto.objects.get()
    variantes = list(produto.variantes.order_by("posicao"))
    assert produto.tipo == Produto.Tipo.VARIAVEL
    assert produto.nome == "Sofa Shopify"
    assert produto.descricao == "<p>Sofa confortavel</p>"
    assert produto.fornecedor == "Moveis FDC"
    assert len(variantes) == 2
    assert variantes[0].price == Decimal("2000.00")
    assert variantes[0].sale_price == Decimal("1800.00")
    assert variantes[0].inventory_quantity == 3
    assert variantes[1].price == Decimal("1999.99")
    assert variantes[1].sale_price is None
    assert variantes[1].inventory_policy == "continue"
    assert TipoVariante.objects.get().nome == "Cor"
    assert [opcao.valor.valor for opcao in variantes[0].opcoes.all()] == ["Bege"]
    assert ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type="variantes"
    ).count() == 2


@pytest.mark.django_db
def test_update_shopify_atualiza_precos_e_estoque_de_todas_as_variantes(conta):
    """Update posterior deve casar variantes pelo ID sem trocar o nome do hub."""
    configuracao = _configuracao(conta)
    dados = _dados()
    processar_webhook(configuracao, "produtos", "create", dados, lambda *_: None)
    dados["title"] = "Nome que nao deve substituir"
    dados["variants"][0].update(price="1700.00", compare_at_price="2100.00",
                                inventory_quantity=8)
    dados["variants"][1].update(price="1900.00", inventory_quantity=20)

    processar_webhook(configuracao, "produtos", "update", dados, lambda *_: None)

    produto = Produto.objects.get()
    bege = VarianteProduto.objects.get(sku="SOFA-BEGE")
    prata = VarianteProduto.objects.get(sku="SOFA-PRATA")
    assert produto.nome == "Sofa Shopify"
    assert (bege.price, bege.sale_price, bege.inventory_quantity) == (
        Decimal("2100.00"), Decimal("1700.00"), 8
    )
    assert (prata.price, prata.sale_price, prata.inventory_quantity) == (
        Decimal("1900.00"), None, 20
    )
