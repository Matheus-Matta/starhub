"""Elegibilidade do cupom por produto, pedido, faixa de valor e horario."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError

from apps.loja.models import Categoria, Cupom, ItemPedido, Pedido, Tag
from apps.loja.services.cupons import itens_elegiveis, pedido_elegivel, vale_para
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
                                value=Decimal("10"), status=Cupom.Status.ATIVO, **campos)


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


def test_faixa_de_preco_filtra_os_itens_que_recebem_desconto(loja):
    """A campanha pode valer so para itens entre R$ 80 e R$ 160."""
    cupom = _cupom(preco_item_minimo=80, preco_item_maximo=160)

    assert not _vale(cupom, loja["camiseta"])
    assert _vale(cupom, loja["tenis"])  # preco promocional atual = R$ 150
    assert _vale(cupom, loja["panela"])


def test_pedido_respeita_maximos_e_quantidade_de_produtos_distintos(loja):
    pedido = Pedido.objects.create(subtotal=Decimal("290"))
    ItemPedido.objects.create(
        pedido=pedido, variante=loja["camiseta"].variante_padrao, quantidade=2, total=100)
    ItemPedido.objects.create(
        pedido=pedido, variante=loja["panela"].variante_padrao, quantidade=1, total=90)
    cupom = _cupom(
        minimum_requirement=Cupom.RequisitoMinimo.AMBOS,
        minimum_subtotal=200, minimum_quantity=3,
        subtotal_maximo=300, quantidade_maxima=4,
        produtos_distintos_minimos=2, produtos_distintos_maximos=3,
    )

    assert pedido_elegivel(cupom, pedido)
    pedido.subtotal = Decimal("301")
    assert not pedido_elegivel(cupom, pedido)


def test_dias_e_horario_aceitam_campanha_que_atravessa_meia_noite(loja):
    cupom = _cupom(dias_semana=["0"], horario_inicio="22:00", horario_fim="06:00")
    pedido = Pedido.objects.create()

    fuso = ZoneInfo("America/Sao_Paulo")
    assert pedido_elegivel(cupom, pedido, datetime(2026, 11, 2, 23, tzinfo=fuso))
    assert pedido_elegivel(cupom, pedido, datetime(2026, 11, 3, 2, tzinfo=fuso))
    assert not pedido_elegivel(cupom, pedido, datetime(2026, 11, 3, 12, tzinfo=fuso))


def test_modelo_recusa_faixas_invertidas():
    cupom = Cupom(
        name="Invalido", discount_type="percentage", value=10,
        minimum_requirement=Cupom.RequisitoMinimo.AMBOS,
        minimum_subtotal=200, subtotal_maximo=100,
        minimum_quantity=5, quantidade_maxima=2,
        preco_item_minimo=80, preco_item_maximo=50,
        produtos_distintos_minimos=3, produtos_distintos_maximos=2,
    )

    with pytest.raises(ValidationError) as erro:
        cupom.full_clean()

    assert set(erro.value.message_dict) >= {
        "subtotal_maximo", "quantidade_maxima", "preco_item_maximo",
        "produtos_distintos_maximos",
    }


def test_admin_exibe_regras_avancadas_sem_json_cru(admin_logado):
    html = admin_logado.get("/admin/loja/cupom/add/").content.decode()

    for campo in (
        "subtotal_maximo", "quantidade_maxima", "produtos_distintos_minimos",
        "produtos_distintos_maximos", "preco_item_minimo", "preco_item_maximo",
        "horario_inicio", "horario_fim",
    ):
        assert f'name="{campo}"' in html
    assert 'name="dias_semana"' in html
    assert "Segunda-feira" in html and "Domingo" in html
