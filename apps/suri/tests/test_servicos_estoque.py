"""Estoque da dimension do servico no Suri: o da peca que ela vende.

    simples                    -> o estoque dele
    variavel (Azul 5, Verde 8) -> Azul + Imper 5, Verde + Imper 8
    kit (bundle: 4 e 9)        -> 9, o maior das pecas
"""

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Categoria, ItemBundle, Produto
from apps.suri.envio.marketplace import SuriMarketplace
from apps.suri.tests.loja_falsa import SuriFalso
from apps.suri.tests.test_servicos_dimensoes import (  # noqa: F401
    _enviar,
    camiseta,
    cfg,
    imper,
)

pytestmark = pytest.mark.django_db


def _estoque(corpo, sku):
    dimensao = next(d for d in corpo["dimensions"] if d["sku"] == sku)
    return dimensao["stocks"]["48346"]["stock"]


def _mudar_estoque(variante, quantidade):
    variante.inventory_quantity = quantidade
    variante.save()


@pytest.fixture
def kit(camiseta, imper):  # noqa: F811
    kit = Produto.objects.create(nome="Kit Camisetas", tipo=Produto.Tipo.BUNDLE)
    kit.categorias.set([Categoria.objects.get(slug="roupas")])
    for sku, quantidade in (("CAM-AZ", 4), ("CAM-VD", 9)):
        variante = camiseta.variantes.get(sku=sku)
        _mudar_estoque(variante, quantidade)
        ItemBundle.objects.create(bundle_product=kit, component_variant=variante)
    imper.regras.get().produtos.add(kit)
    return kit


def test_servico_do_produto_simples_tem_o_estoque_dele(cfg, monkeypatch, camiseta, imper):  # noqa: F811
    camiseta.tipo = Produto.Tipo.SIMPLES
    camiseta.save()
    camiseta.variantes.exclude(sku="CAM-AZ").delete()
    _mudar_estoque(camiseta.variantes.get(), 7)

    _, corpo = _enviar(cfg, monkeypatch, camiseta)

    assert _estoque(corpo, "IMP") == 7


def test_servico_de_cada_cor_tem_o_estoque_da_cor(
        cfg, monkeypatch, camiseta, imper):  # noqa: F811
    """Com o servico preso a Azul, ia o maior estoque (8) e a Azul vendia sem ter."""
    _mudar_estoque(camiseta.variantes.get(sku="CAM-VD"), 8)

    _, corpo = _enviar(cfg, monkeypatch, camiseta)

    assert [_estoque(corpo, sku) for sku in ("CAM-AZ", "CAM-VD", "IMP", "IMP-CAM-VD")] == [
        5, 8, 5, 8]


def test_estoque_da_variacao_atualiza_o_servico_dela(
        cfg, monkeypatch, camiseta, imper):  # noqa: F811
    """A baixa da Verde (que nao e a padrao) nao mexia no servico dela no Suri."""
    loja, _ = _enviar(cfg, monkeypatch, camiseta)
    verde = camiseta.variantes.get(sku="CAM-VD")
    _mudar_estoque(verde, 12)

    SuriMarketplace(cfg).enviar("estoque", "update", verde.pk)

    metodo, rota, corpo = loja.chamadas[-1]
    assert (metodo, rota) == ("PUT", "shop/products/48349/stocks")
    assert {s["sku"]: s["stocks"]["48346"]["stock"] for s in corpo["skus"]} == {
        "CAM-VD": 12, "IMP-CAM-VD": 12}


def test_servico_do_kit_tem_o_maior_estoque_dos_itens(cfg, monkeypatch, kit):  # noqa: F811
    _, corpo = _enviar(cfg, monkeypatch, kit)

    assert _estoque(corpo, "IMP") == 9


def test_estoque_do_item_atualiza_o_servico_do_kit(cfg, monkeypatch, camiseta, kit):  # noqa: F811
    """O item do kit muda de estoque e o kit nao e salvo: o servico dele no Suri ficava
    com o numero velho."""
    loja = SuriFalso().instalar(monkeypatch)
    SuriMarketplace(cfg).enviar("produtos", "create", kit.pk)
    kit_no_suri = ExternalReference.objects.get(
        platform="suri", entity_type="produtos", object_id=str(kit.pk)).external_id
    verde = camiseta.variantes.get(sku="CAM-VD")
    _mudar_estoque(verde, 15)

    SuriMarketplace(cfg).enviar("estoque", "update", verde.pk)

    do_kit = [c for m, rota, c in loja.chamadas
              if rota == f"shop/products/{kit_no_suri}/stocks"]
    assert do_kit and do_kit[-1] == {"skus": [{"sku": "IMP", "stocks": {"48346": {"stock": 15}}}]}
