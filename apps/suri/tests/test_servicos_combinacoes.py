"""Servicos combinados no Suri: toda cor com toda escolha de servico, um de cada categoria.

    Camiseta Azul (padrao, R$ 49,90) e Verde (R$ 59,90)
    + Instalacao (Completa R$ 40, Simples R$ 20) + Impermeabilizacao (Imper R$ 30)
    -> 2 cores x 3 opcoes de Instalacao x 2 de Impermeabilizacao = 12 dimensions
       INS1-IMP-CAM-VD  Verde + Simples + Imper  R$ 109,90  estoque da Verde
       IMP              Azul + Imper (so ele)    SKU do servico: pedido antigo segue valendo
"""

from decimal import Decimal

import pytest

from apps.loja.services.extras_pedido import extras
from apps.suri.contexto import usando_configuracao
from apps.suri.envio.marketplace import SuriMarketplace
from apps.suri.importar_pedidos import importar_pedido
from apps.suri.tests.loja_falsa import pedido
from apps.suri.tests.test_servicos_categorias import servicos  # noqa: F401
from apps.suri.tests.test_servicos_dimensoes import _enviar, camiseta, cfg  # noqa: F401

pytestmark = pytest.mark.django_db


def _mudar_estoque(variante, quantidade):
    variante.inventory_quantity = quantidade
    variante.save()


def test_toda_cor_combina_com_um_servico_de_cada_categoria(
        cfg, monkeypatch, camiseta, servicos):  # noqa: F811
    """So a cor padrao levava servico, e um servico por vez: no Suri, Verde + Imper ou
    Simples + Imper nao existiam e o cliente nao conseguia comprar."""
    _mudar_estoque(camiseta.variantes.get(sku="CAM-VD"), 8)

    _, corpo = _enviar(cfg, monkeypatch, camiseta)

    por_sku = {d["sku"]: d for d in corpo["dimensions"]}
    assert len(por_sku) == 12
    escolhas = {tuple(d["dimensions"].values()) for d in corpo["dimensions"]}
    assert len(escolhas) == 12, "cada combinacao de cor e servicos aparece uma vez"
    verde, combinado = por_sku["CAM-VD"], por_sku["INS1-IMP-CAM-VD"]
    assert combinado["dimensions"] == {"Cor": "Verde", "Instalação": "Simples (R$ 20,00)",
                                       "Impermeabilização": "Imper (R$ 30,00)"}
    assert combinado["price"] == verde["price"] + Decimal("50.00")
    assert combinado["stocks"] == verde["stocks"]
    assert por_sku["IMP"]["dimensions"] == {
        "Cor": "Azul", "Instalação": "Sem serviço", "Impermeabilização": "Imper (R$ 30,00)"}


def test_pedido_com_dois_servicos_vira_item_da_cor_e_os_dois_servicos(
        cfg, monkeypatch, camiseta, servicos):  # noqa: F811
    _enviar(cfg, monkeypatch, camiseta)
    linha = {"providerId": "48349", "sku": "INS1-IMP-CAM-VD",
             "name": "Camiseta (Verde, Simples, Imper)", "quantity": Decimal("1"),
             "unitPrice": Decimal("109.90"), "subTotalAmount": Decimal("109.90"),
             "totalAmout": Decimal("109.90"), "discountAmout": Decimal("0")}

    with usando_configuracao(cfg):
        obj, _ = importar_pedido(pedido(items=[linha], totalAmount=Decimal("119.90"),
                                        discountAmount=Decimal("0")))

    item = obj.itens.get()
    assert (item.variante.sku, item.preco_unitario, item.total) == (
        "CAM-VD", Decimal("59.90"), Decimal("59.90"))
    assert sorted((s["servico"], s["preco"]) for s in extras(obj)["servicos"]) == [
        ("Imper", "30.00"), ("Simples", "20.00")]


def test_baixa_da_cor_atualiza_so_as_dimensions_dela(
        cfg, monkeypatch, camiseta, servicos):  # noqa: F811
    """O estoque da Verde nao pode mudar o Azul + servico, que vende outra peca."""
    loja, _ = _enviar(cfg, monkeypatch, camiseta)
    verde = camiseta.variantes.get(sku="CAM-VD")
    _mudar_estoque(verde, 12)

    SuriMarketplace(cfg).enviar("estoque", "update", verde.pk)

    metodo, rota, corpo = loja.chamadas[-1]
    estoques = {s["sku"]: s["stocks"]["48346"]["stock"] for s in corpo["skus"]}
    assert (metodo, rota) == ("PUT", "shop/products/48349/stocks")
    assert len(estoques) == 6 and set(estoques.values()) == {12}
    assert all(sku == "CAM-VD" or sku.endswith("-CAM-VD") for sku in estoques)
