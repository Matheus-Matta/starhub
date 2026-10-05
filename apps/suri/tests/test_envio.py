"""Envio do hub para o Suri Shop: categoria, produto, estoque e status do pedido."""

import json
from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Categoria, Pedido
from apps.suri.cliente import SuriErro, _json
from apps.suri.envio.marketplace import SuriMarketplace
from apps.suri.importar_catalogo import importar_produto
from apps.suri.importar_pedidos import importar_pedido
from apps.suri.tests.loja_falsa import SuriFalso, configuracao, pedido, produto

pytestmark = pytest.mark.django_db
ENVIA = tuple((r, o) for r in ("produtos", "estoque", "categorias", "pedidos")
              for o in ("create", "update", "delete"))


def _marketplace(conta, monkeypatch):
    loja = SuriFalso().instalar(monkeypatch)
    return SuriMarketplace(configuracao(conta, enviar=ENVIA)), loja


def _produto_do_hub():
    obj, _ = importar_produto(produto())
    ExternalReference.objects.filter(platform="suri").delete()
    roupas = Categoria.objects.create(nome="Roupas", slug="roupas")
    camisetas = Categoria.objects.create(nome="Camisetas", slug="camisetas", pai=roupas)
    obj.categorias.set([camisetas])
    return obj, roupas, camisetas


def test_preco_vai_como_numero_exato_sem_passar_por_float():
    assert json.loads(_json({"price": Decimal("49.90")})) == {"price": 49.9}
    assert b'"price": 49.90' in _json({"price": Decimal("49.90")})


def test_produto_novo_leva_a_arvore_da_categoria_antes(conta, monkeypatch):
    """O Suri recusa produto de categoria que ele nao tem."""
    marketplace, loja = _marketplace(conta, monkeypatch)
    obj, roupas, camisetas = _produto_do_hub()

    marketplace.enviar("produtos", "create", obj.pk)

    rotas = [(m, r) for m, r, _ in loja.chamadas if m != "GET"]
    assert rotas == [("POST", "shop/categories"), ("POST", "shop/products")]
    categoria = loja.chamadas[-2][2]
    assert categoria["id"] == f"sh-{roupas.pk}"
    assert categoria["children"][0]["id"] == f"sh-{camisetas.pk}"
    corpo = loja.chamadas[-1][2]
    assert (corpo["id"], corpo["categoryId"], corpo["subcategoryId"]) == (
        f"sh-{obj.pk}", f"sh-{roupas.pk}", f"sh-{camisetas.pk}")
    azul = next(d for d in corpo["dimensions"] if d["sku"] == "CAM-AZ")
    assert azul["price"] == Decimal("49.90") and azul["dimensions"] == {"Cor": "Azul"}
    assert azul["stocks"] == {"48346": {"stock": 5}}
    assert "images" not in corpo, "sem foto publica, as fotos do Suri nao sao apagadas"


def test_produto_sem_categoria_explica_o_que_fazer(conta, monkeypatch):
    marketplace, _ = _marketplace(conta, monkeypatch)
    obj, _, _ = _produto_do_hub()
    obj.categorias.clear()

    with pytest.raises(SuriErro, match="categoria"):
        marketplace.enviar("produtos", "create", obj.pk)


def test_estoque_vai_so_do_sku_na_loja_do_estoque(conta, monkeypatch):
    marketplace, loja = _marketplace(conta, monkeypatch)
    obj, _ = importar_produto(produto())
    azul = obj.variantes.get(sku="CAM-AZ")

    marketplace.enviar("estoque", "update", azul.pk)

    assert loja.chamadas[-1] == ("PUT", "shop/products/48349/stocks", {
        "skus": [{"sku": "CAM-AZ", "stocks": {"48346": {"stock": 5}}}]})


def test_pedido_pago_no_suri_nao_e_marcado_pago_de_novo(conta, monkeypatch):
    """Sem o estado no vinculo, cada save do pedido chamaria /paid de novo."""
    marketplace, loja = _marketplace(conta, monkeypatch)
    importar_produto(produto())
    obj, _ = importar_pedido(pedido())
    Pedido.objects.filter(pk=obj.pk).update(status=Pedido.Status.CONCLUIDO)

    marketplace.enviar("pedidos", "update", obj.pk)
    marketplace.enviar("pedidos", "update", obj.pk)

    assert [r for m, r, _ in loja.chamadas if m == "POST"] == ["shop/orders/logistic"]


def test_cancelar_no_hub_cancela_no_suri(conta, monkeypatch):
    marketplace, loja = _marketplace(conta, monkeypatch)
    importar_produto(produto())
    obj, _ = importar_pedido(pedido(status=1))
    Pedido.objects.filter(pk=obj.pk).update(status=Pedido.Status.CANCELADO)

    marketplace.enviar("pedidos", "update", obj.pk)

    assert loja.chamadas[-1] == ("POST", "shop/orders/cancel", {"orderId": "51807"})
