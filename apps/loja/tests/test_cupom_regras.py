"""Regras de produto do cupom: elegibilidade + excecoes (apps/loja/services/cupons.py)
e o form que recusa o mesmo produto incluido e excluido."""

from decimal import Decimal

import pytest

from apps.loja.models import Categoria, Cupom, Tag
from apps.loja.services.cupons import itens_elegiveis, vale_para
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db


@pytest.fixture
def loja():
    moda = Categoria.objects.create(nome="Moda", slug="moda")
    casa = Categoria.objects.create(nome="Casa", slug="casa")
    camiseta = criar_produto("Camiseta", sku="CAM", price=Decimal("50"))
    tenis = criar_produto("Tenis", sku="TEN", price=Decimal("200"), sale_price=Decimal("150"))
    panela = criar_produto("Panela", sku="PAN", price=Decimal("90"))
    camiseta.categorias.set([moda])
    tenis.categorias.set([moda])
    panela.categorias.set([casa])
    return {"moda": moda, "casa": casa, "camiseta": camiseta, "tenis": tenis, "panela": panela}


def _cupom(**campos):
    return Cupom.objects.create(name="Cupom", discount_type="percentage",
                                value=Decimal("10"), **campos)


def _vale(cupom, produto):
    return vale_para(cupom, produto.variante_padrao)


def test_sem_regra_vale_para_tudo(loja):
    cupom = _cupom()
    assert all(_vale(cupom, loja[n]) for n in ("camiseta", "tenis", "panela"))


def test_so_produtos_escolhidos(loja):
    cupom = _cupom(product_eligibility="specific_products")
    cupom.produtos.set([loja["camiseta"]])
    assert _vale(cupom, loja["camiseta"]) and not _vale(cupom, loja["panela"])


def test_categoria_menos_produto_excluido_e_promocao(loja):
    cupom = _cupom(product_eligibility="categories", excluir_promocao=True)
    cupom.categorias.set([loja["moda"]])
    assert _vale(cupom, loja["camiseta"])
    assert not _vale(cupom, loja["tenis"])  # em promocao
    assert not _vale(cupom, loja["panela"])  # fora da categoria
    cupom.produtos_excluidos.set([loja["camiseta"]])
    assert not _vale(cupom, loja["camiseta"])


def test_categoria_excluida_e_tags(loja):
    promo = Tag.objects.create(nome="Promo")
    loja["panela"].tags.set([promo])
    cupom = _cupom(product_eligibility="product_tags")
    cupom.tags.set([promo])
    assert _vale(cupom, loja["panela"]) and not _vale(cupom, loja["camiseta"])
    cupom.categorias_excluidas.set([loja["casa"]])
    assert not _vale(cupom, loja["panela"])


def test_itens_elegiveis_filtra_os_itens_do_pedido(loja):
    from apps.loja.models import ItemPedido, Pedido

    pedido = Pedido.objects.create()
    for nome in ("camiseta", "panela"):
        ItemPedido.objects.create(pedido=pedido, variante=loja[nome].variante_padrao, total=10)
    cupom = _cupom(product_eligibility="specific_products")
    cupom.produtos.set([loja["panela"]])
    assert [i.nome for i in itens_elegiveis(cupom, pedido.itens.all())] == ["Panela"]


def test_admin_recusa_produto_incluido_e_excluido(admin_logado, loja):
    camiseta = loja["camiseta"]
    dados = {"name": "X", "status": "active", "currency": "BRL",
             "discount_type": "percentage", "value": "10", "stacking_policy": "deny",
             "minimum_requirement": "none", "customer_eligibility": "all",
             "product_eligibility": "specific_products", "produtos": [camiseta.pk],
             "produtos_excluidos": [camiseta.pk], "metadados": "[]"}
    resposta = admin_logado.post("/admin/loja/cupom/add/", dados)
    assert resposta.status_code == 200
    assert "produtos_excluidos" in resposta.context["adminform"].form.errors
