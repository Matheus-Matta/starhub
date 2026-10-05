"""Catalogo e pedidos do Suri Shop no hub."""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Categoria, ItemPedido, Pedido, Produto
from apps.suri.contexto import coletando_avisos, usando_configuracao
from apps.suri.importar_catalogo import importar_categorias, importar_produto
from apps.suri.importar_pedidos import PedidoIgnorado, importar_pedido
from apps.suri.tests.loja_falsa import SuriFalso, configuracao, pedido, produto

pytestmark = pytest.mark.django_db


def test_arvore_de_categorias_entra_com_a_pai():
    mapa = importar_categorias([{"id": "1", "name": "Roupas", "children": [
        {"id": "2", "name": "Camisetas", "children": []}]}])

    assert mapa["2"].pai == mapa["1"] and Categoria.objects.count() == 2


def test_produto_com_atributos_vira_variavel_com_uma_variante_por_sku():
    importar_categorias([{"id": "48348", "name": "Roupas", "children": []}])

    obj, criado = importar_produto(produto())

    azul = obj.variantes.get(sku="CAM-AZ")
    assert criado and obj.tipo == Produto.Tipo.VARIAVEL and obj.variantes.count() == 2
    assert azul.price == Decimal("49.90") and azul.weight == Decimal("0.25")
    assert azul.inventory_quantity == 5, "o hub tem um estoque so: a soma das lojas"
    assert azul.opcoes.get().valor.valor == "Azul"
    assert list(obj.categorias.values_list("nome", flat=True)) == ["Roupas"]
    assert ExternalReference.objects.get(entity_type="variantes",
                                         external_id="48349:CAM-AZ").external_parent_id == "48349"


def test_produto_simples_usa_a_variante_padrao_e_nao_duplica():
    simples = produto(attributes=[], dimensions=[
        {"sku": "BEB-1", "dimensions": {}, "price": Decimal("37.5"),
         "stocks": {"48346": {"stock": 9}}}])
    importar_produto(simples)

    obj, criado = importar_produto(simples)

    assert not criado and Produto.objects.count() == 1 and obj.variantes.count() == 1
    assert obj.variante_padrao.sku == "BEB-1"


def test_pedido_pago_entra_com_valores_exatos_desconto_e_frete():
    importar_produto(produto())

    obj, criado = importar_pedido(pedido())

    item = obj.itens.get()
    assert criado and obj.status == "processing" and obj.financial_status == "paid"
    assert (item.quantidade, item.subtotal, item.variante.sku) == (2, Decimal("99.80"), "CAM-AZ")
    assert obj.total_frete == Decimal("10.00")
    assert obj.total == Decimal("104.80"), "itens + frete - desconto do pedido = total do Suri"
    assert obj.forma_pagamento == "pix" and obj.cliente.cpf == "52998224725"
    assert obj.endereco_entrega.city == "Fortaleza"


def test_pedido_repetido_atualiza_e_entregue_conclui():
    importar_produto(produto())
    importar_pedido(pedido())

    obj, criado = importar_pedido(pedido(logistic={"name": "Entrega", "price": Decimal("10"),
                                                   "status": 4}))

    assert not criado and Pedido.objects.count() == 1 and ItemPedido.objects.count() == 1
    assert obj.status == "completed"
    vinculo = ExternalReference.objects.get(platform="suri", entity_type="pedidos")
    assert vinculo.metadata == {"pago": True, "cancelado": False, "logistica": 4}


def test_carrinho_em_andamento_nao_vira_pedido():
    with pytest.raises(PedidoIgnorado):
        importar_pedido(pedido(status=0))

    assert not Pedido.objects.exists()


def test_comprador_sem_email_fica_sem_cliente_mas_com_endereco():
    """Venda pelo WhatsApp: sem e-mail o Cliente do hub nao existe, o pedido sim."""
    importar_produto(produto())
    comprador = {**pedido()["customer"], "email": None}

    obj, _ = importar_pedido(pedido(customer=comprador))

    assert obj.cliente is None and obj.endereco_entrega.city == "Fortaleza"


def test_produto_que_o_hub_nao_tem_e_buscado_no_suri(conta, monkeypatch):
    SuriFalso(produtos=[produto()]).instalar(monkeypatch)

    with usando_configuracao(configuracao(conta)):
        obj, _ = importar_pedido(pedido())

    assert obj.itens.get().variante.sku == "CAM-AZ"


def test_quantidade_fracionada_vira_aviso():
    importar_produto(produto())
    item = {**pedido()["items"][0], "quantity": Decimal("1.5")}

    with coletando_avisos() as avisos:
        importar_pedido(pedido(items=[item]))

    assert "fracionada" in avisos[0]["motivo"]
