"""Produto da loja WooCommerce no catalogo do hub (simples e variavel)."""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Categoria, Produto, VarianteProduto
from apps.woocommerce.contexto import coletando_avisos
from apps.woocommerce.importar_produtos import importar_produto
from apps.woocommerce.tests import exemplos

pytestmark = pytest.mark.django_db


def test_produto_simples_entra_com_preco_estoque_categoria_e_vinculo():
    produto, criado = importar_produto(exemplos.produto_simples())

    variante = produto.variante_padrao
    assert criado and produto.nome == "Sofa Azul" and produto.tipo == "simple"
    assert (variante.sku, variante.price, variante.sale_price) == (
        "SOFA-1", Decimal("1999.90"), Decimal("1799.90"))
    assert variante.inventory_quantity == 7 and variante.weight == Decimal("30.5")
    assert list(produto.categorias.values_list("nome", flat=True)) == ["Sofas"]
    assert list(produto.tags.values_list("nome", flat=True)) == ["Sala"]
    assert ExternalReference.objects.filter(platform="woocommerce", entity_type="produtos",
                                            external_id="15").exists()


def test_produto_que_chega_de_novo_atualiza_sem_duplicar():
    """Webhook repetido criava um segundo produto e uma segunda categoria."""
    importar_produto(exemplos.produto_simples())

    produto, criado = importar_produto(exemplos.produto_simples(stock_quantity=2))

    assert not criado
    assert Produto.objects.count() == 1 and Categoria.objects.count() == 1
    assert produto.variante_padrao.inventory_quantity == 2


def test_webhook_nao_sobrescreve_o_nome_ajustado_no_hub_mas_atualiza_o_preco():
    produto, _ = importar_produto(exemplos.produto_simples())
    Produto.objects.filter(pk=produto.pk).update(nome="Sofa do hub")

    importar_produto(exemplos.produto_simples(name="Sofa da loja", regular_price="10.00"))

    produto.refresh_from_db()
    assert produto.nome == "Sofa do hub"
    assert produto.variante_padrao.price == Decimal("10.00")


def test_sincronizacao_sobrescreve_o_nome():
    produto, _ = importar_produto(exemplos.produto_simples())

    importar_produto(exemplos.produto_simples(name="Sofa da loja"), sobrescrever=True)

    produto.refresh_from_db()
    assert produto.nome == "Sofa da loja"


def test_produto_variavel_cria_uma_variante_por_variacao_com_a_opcao():
    variacoes = [exemplos.variacao(21, "Azul", "CAM-AZ", "49.90", 3),
                 exemplos.variacao(22, "Verde", "CAM-VD", "59.90", 0)]

    produto, _ = importar_produto(exemplos.produto_variavel(), variacoes)

    variantes = list(produto.variantes.order_by("posicao"))
    assert [(v.sku, v.price, v.titulo) for v in variantes] == [
        ("CAM-AZ", Decimal("49.90"), "Azul"), ("CAM-VD", Decimal("59.90"), "Verde")]
    assert [v.opcoes.get().valor.valor for v in variantes] == ["Azul", "Verde"]
    vinculo = ExternalReference.objects.get(entity_type="variantes", external_id="22")
    assert vinculo.external_parent_id == "20"


def test_sku_de_outra_variante_do_hub_vira_aviso_e_nao_quebra():
    """SKU repetido estourava o produto inteiro; agora mantem o do hub e avisa."""
    importar_produto(exemplos.produto_simples())
    outro = exemplos.produto_simples(id=16, slug="outro", name="Outro", sku="")
    produto, _ = importar_produto(outro)
    produto.variante_padrao.sku = ""

    with coletando_avisos() as avisos:
        importar_produto({**outro, "sku": "SOFA-1"}, sobrescrever=True)

    assert VarianteProduto.objects.filter(sku="SOFA-1").count() == 1
    assert "SOFA-1" in avisos[0]["motivo"]
