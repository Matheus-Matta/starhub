from decimal import Decimal

import pytest

from apps.loja.dinheiro import ValorInvalido, dinheiro
from apps.loja.models import ItemPedido, Pedido, VarianteProduto
from apps.loja.services.variantes import criar_produto
from apps.loja.totais import recalcular_totais, valores_do_item


def test_dinheiro_recusa_float():
    """float chega com o centavo torto (0.1 + 0.2 = 0.30000000000000004)."""
    with pytest.raises(ValorInvalido):
        dinheiro(0.1)


def test_dinheiro_arredonda_meio_para_cima():
    assert dinheiro("9.045") == Decimal("9.05")
    assert dinheiro("19.9") == Decimal("19.90")


def test_total_zero_com_subtotal_e_desconto_de_100_por_cento():
    """total=0 e informacao (brinde), nao "campo vazio". Testar com `or` no
    lugar de `is None` trocaria o 0 pelo subtotal e cobraria o brinde."""
    subtotal, total = valores_do_item(Decimal("10.00"), 1, None, Decimal("0"))
    assert (subtotal, total) == (Decimal("10.00"), Decimal("0.00"))


@pytest.mark.django_db
def test_total_do_pedido_soma_as_linhas_ja_arredondadas():
    """Dois itens de R$ 10,05 com 10% de desconto: 9,05 + 9,05 = 18,10.
    Arredondar so no fim (20,10 x 0,9 = 18,09) perde um centavo."""
    pedido = Pedido.objects.create()
    for _ in range(2):
        ItemPedido.objects.create(pedido=pedido, subtotal=Decimal("10.05"),
                                  total=dinheiro(Decimal("10.05") * Decimal("0.9")))
    pedido.linhas_frete = [{"total": "15.00", "total_tax": "0.00"}]
    recalcular_totais(pedido)
    pedido.refresh_from_db()
    assert pedido.total == Decimal("33.10")
    assert pedido.total_desconto == Decimal("2.00")


@pytest.mark.django_db
@pytest.mark.parametrize(("estoque", "politica", "esperado"), [
    (3, "deny", "instock"),
    (0, "deny", "outofstock"),
    (0, "continue", "onbackorder"),
])
def test_situacao_do_estoque_sai_da_quantidade(estoque, politica, esperado):
    produto = criar_produto("P", inventory_quantity=estoque, inventory_policy=politica)
    assert produto.situacao_estoque == esperado


@pytest.mark.django_db
def test_sku_repetido_na_mesma_conta_e_barrado_pelo_banco():
    from django.db import IntegrityError

    criar_produto("A", sku="X1")
    with pytest.raises(IntegrityError):
        criar_produto("B", sku="X1")


@pytest.mark.django_db
def test_varios_produtos_sem_sku_sao_permitidos():
    criar_produto("A")
    criar_produto("B")
    assert VarianteProduto.objects.filter(sku="").count() == 2
