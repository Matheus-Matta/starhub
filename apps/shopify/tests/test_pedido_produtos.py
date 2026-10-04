import sys
import types
from decimal import Decimal

import pytest

from apps.core.models import ExternalReference, Origin
from apps.loja.models import Pedido
from apps.loja.services.variantes import criar_produto
from apps.shopify.pedidos import importar_pedido
from apps.shopify.tests.pedido_exemplo import pedido_shopify, produto_shopify_falso  # noqa: F401


class FalhaNoShopify(Exception):
    pass


def _trocar_busca(monkeypatch, funcao):
    modulo = types.SimpleNamespace(garantir_produto=funcao)
    monkeypatch.setitem(sys.modules, "apps.shopify.pedidos_produtos", modulo)


@pytest.mark.django_db
def test_item_sem_cadastro_pede_o_produto_ao_shopify_e_liga_na_variante(monkeypatch):
    """Item solto nao baixa estoque nem conta venda: o produto tem que ser importado."""
    importado = criar_produto("Almofada", sku="ALMOFADA-IMPORTADA", price=Decimal("50.00"))
    pedidas = []

    def garantir_produto(linha):
        pedidas.append(linha["sku"])
        return importado.variante_padrao if linha["sku"] == "ALMOFADA-SEM-CADASTRO" else None

    _trocar_busca(monkeypatch, garantir_produto)
    pedido, _ = importar_pedido(pedido_shopify())

    assert pedidas == ["POLTRONA-001", "ALMOFADA-SEM-CADASTRO"]
    almofada = pedido.itens.get(sku="ALMOFADA-SEM-CADASTRO")
    assert (almofada.produto, almofada.variante) == (importado, importado.variante_padrao)
    assert pedido.itens.get(sku="POLTRONA-001").produto is None


@pytest.mark.django_db
def test_variante_referenciada_no_shopify_vale_mais_que_o_sku(produto_shopify_falso):  # noqa: F811
    """SKU repetido/trocado no Shopify nao pode ligar o item a outro produto."""
    certo = criar_produto("Poltrona certa", sku="OUTRO-SKU", price=Decimal("1.00"))
    criar_produto("Poltrona errada", sku="POLTRONA-001", price=Decimal("1.00"))
    ExternalReference.objects.create(
        platform=Origin.SHOPIFY, entity_type="variantes",
        external_id="gid://shopify/ProductVariant/9001", object_id=str(certo.variante_padrao.pk))

    pedido, _ = importar_pedido(pedido_shopify())

    assert pedido.itens.get(sku="POLTRONA-001").produto == certo
    assert [linha["sku"] for linha in produto_shopify_falso] == ["ALMOFADA-SEM-CADASTRO"]


@pytest.mark.django_db
def test_falha_ao_buscar_produto_desfaz_o_pedido_inteiro(monkeypatch):
    """Pedido gravado pela metade some da fila de reprocessamento e fica sem o item."""
    def garantir_produto(_linha):
        raise FalhaNoShopify("API fora do ar")

    _trocar_busca(monkeypatch, garantir_produto)

    with pytest.raises(FalhaNoShopify):
        importar_pedido(pedido_shopify())

    assert not Pedido.objects.exists()
