"""Regras do servico: a quais produtos ele vale e por qual preco, pela ordem."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.loja.models import Categoria, Pedido, RegraServico, Servico
from apps.loja.services.extras_pedido import mesclar_extras
from apps.loja.services.servicos import preencher_precos_dos_pedidos
from apps.loja.services.servicos_regras import (
    produtos_da_regra,
    proxima_ordem,
    servicos_do_produto,
)
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalogo():
    sofas = Categoria.objects.create(nome="Sofas", slug="sofas")
    barato = criar_produto("Sofa compacto", sku="SOF-1", price=Decimal("1500.00"))
    caro = criar_produto("Sofa retratil", sku="SOF-2", price=Decimal("4500.00"))
    mesa = criar_produto("Mesa de centro", sku="MES-1", price=Decimal("800.00"))
    barato.categorias.add(sofas)
    caro.categorias.add(sofas)
    return sofas, barato, caro, mesa


@pytest.fixture
def montagem():
    return Servico.objects.create(nome="Montagem", preco=Decimal("120.00"))


def _regra(servico, ordem, produtos=(), categorias=(), **campos):
    regra = RegraServico.objects.create(servico=servico, ordem=ordem, **campos)
    regra.produtos.set(produtos)
    regra.categorias.set(categorias)
    return regra


def test_categoria_e_faixa_de_preco_valem_juntas(catalogo, montagem):
    sofas, barato, caro, mesa = catalogo
    regra = _regra(montagem, 10, categorias=[sofas], preco_ate=Decimal("2000.00"))

    assert list(produtos_da_regra(regra)) == [barato]


def test_produto_escolhido_direto_entra_mesmo_fora_das_outras_regras(catalogo, montagem):
    _, _, _, mesa = catalogo
    regra = _regra(montagem, 10, produtos=[mesa])

    assert list(produtos_da_regra(regra)) == [mesa]


def test_produto_escolhido_soma_com_a_selecao_dinamica(catalogo, montagem):
    """Escolher a mesa a mao inclui a mesa; nao exige que ela seja da categoria."""
    sofas, barato, caro, mesa = catalogo
    regra = _regra(montagem, 10, produtos=[mesa], categorias=[sofas],
                   preco_ate=Decimal("2000.00"))

    assert list(produtos_da_regra(regra)) == [mesa, barato]


def test_primeira_regra_na_ordem_define_o_preco_do_produto(catalogo, montagem):
    """Sofa caro casa nas duas regras: vale a de menor ordem, mesmo criada depois."""
    sofas, barato, caro, mesa = catalogo
    _regra(montagem, 20, categorias=[sofas], preco=Decimal("150.00"))
    _regra(montagem, 10, categorias=[sofas], preco_de=Decimal("3000.00"),
           preco=Decimal("250.00"))

    assert servicos_do_produto(caro) == [(montagem, Decimal("250.00"))]
    assert servicos_do_produto(barato) == [(montagem, Decimal("150.00"))]
    assert servicos_do_produto(mesa) == []


def test_regra_sem_preco_usa_o_preco_padrao_do_servico(catalogo, montagem):
    _, _, _, mesa = catalogo
    _regra(montagem, 10, produtos=[mesa])

    assert servicos_do_produto(mesa) == [(montagem, Decimal("120.00"))]


def test_regra_ou_servico_inativo_nao_vale(catalogo, montagem):
    _, _, _, mesa = catalogo
    regra = _regra(montagem, 10, produtos=[mesa], active=False)
    assert servicos_do_produto(mesa) == []
    regra.active = True
    regra.save()
    montagem.active = False
    montagem.save()
    assert servicos_do_produto(mesa) == []


def test_regra_sem_nenhum_criterio_e_recusada(montagem):
    """Regra vazia valeria para o catalogo inteiro sem ninguem ter escolhido isso."""
    regra = RegraServico(servico=montagem, ordem=10)
    with pytest.raises(ValidationError, match="Escolha produtos, categorias ou uma faixa"):
        regra.validar_criterios(produtos=[], categorias=[])


def test_faixa_com_minimo_maior_que_maximo_e_recusada(montagem):
    regra = RegraServico(servico=montagem, ordem=10, preco_de=Decimal("500"),
                         preco_ate=Decimal("100"))
    with pytest.raises(ValidationError, match="minimo"):
        regra.clean()


def test_proxima_ordem_fica_depois_da_ultima_de_dez_em_dez(montagem):
    assert proxima_ordem(montagem) == 10
    RegraServico.objects.create(servico=montagem, ordem=35, preco_de=Decimal("1"))
    assert proxima_ordem(montagem) == 45


def test_servico_sem_preco_recebe_o_ultimo_preco_pago_em_pedido(conta):
    """Servico criado sozinho pelo pedido nascia sem preco; o pedido sabe quanto custou."""
    garantia = Servico.objects.create(nome="Garantia estendida")
    for preco in ("99.90", "149.90"):
        pedido = Pedido.objects.create()
        mesclar_extras(pedido, {"servicos": [{"item_id": 1, "servico": "Garantia estendida",
                                              "servico_id": garantia.pk, "preco": preco}]})
        pedido.save()
    nunca_vendido = Servico.objects.create(nome="Higienizacao")

    assert preencher_precos_dos_pedidos(Pedido, Servico) == 1
    garantia.refresh_from_db()
    nunca_vendido.refresh_from_db()
    assert garantia.preco == Decimal("149.90")
    assert nunca_vendido.preco == Decimal("0.00")
