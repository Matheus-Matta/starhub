"""Servico do app Easify na propriedade do item: o SKU vem no fim do nome.

    {"name": "_IMPER ATÉ 2,5M_2432", "value": "IMPERMEABILIZAÇÃO [ +R$ 499,99 ]"}
    -> servico "IMPER ATÉ 2,5M", SKU "2432", opcao "IMPERMEABILIZAÇÃO", preco 499.99

O vinculo com o cadastro de Servicos e pelo SKU: pelo nome, todo servico com "imper"
caia no mesmo cadastro e o ERP nao distinguia a impermeabilizacao de 2,5 m da de 3 m.
"""

from decimal import Decimal

import pytest

from apps.loja.models import Servico
from apps.loja.services.servicos import vincular
from apps.shopify.pedidos_servicos import servicos_do_item

EASIFY = [
    {"name": "_IMPER ATÉ 2,5M_2432", "value": "IMPERMEABILIZAÇÃO [ +R$ 499,99 ]"},
    {"name": "_tpo_add_by", "value": "easify"},
]


def _do_pedido(**extra):
    return {"item_id": 7, "sku": "2779", "servico": "IMPER ATÉ 2,5M", "_sku": "2432",
            "opcao": "IMPERMEABILIZAÇÃO", "preco": "499.99", "somado": True, **extra}


def test_nome_da_propriedade_do_easify_separa_nome_e_sku():
    assert servicos_do_item(EASIFY) == [{
        "servico": "IMPER ATÉ 2,5M", "_sku": "2432",
        "opcao": "IMPERMEABILIZAÇÃO", "preco": Decimal("499.99"),
    }]


@pytest.mark.django_db
def test_servico_sem_cadastro_nasce_com_o_sku_nome_e_preco_do_easify(conta):
    """Sem o SKU do Easify o cadastro nascia SERV-<NOME> e o ERP nao reconhecia."""
    [servico] = vincular([_do_pedido()])

    cadastro = Servico.objects.get()
    assert (cadastro.sku, cadastro.nome, cadastro.preco) == (
        "2432", "IMPER ATÉ 2,5M", Decimal("499.99"))
    assert servico == {"item_id": 7, "sku": "2779", "servico": "IMPER ATÉ 2,5M",
                       "servico_id": cadastro.pk, "opcao": "IMPERMEABILIZAÇÃO",
                       "preco": "499.99", "somado": True}


@pytest.mark.django_db
def test_servico_ja_cadastrado_e_achado_pelo_sku_mesmo_com_outro_nome(conta):
    """O operador renomeia o cadastro: o pedido seguinte nao pode criar outro."""
    cadastro = Servico.objects.create(nome="Impermeabilização 2,5 m", sku="2432",
                                      preco=Decimal("450.00"))

    [servico] = vincular([_do_pedido()])

    assert Servico.objects.count() == 1
    assert (servico["servico_id"], servico["servico"]) == (cadastro.pk,
                                                            "Impermeabilização 2,5 m")
    cadastro.refresh_from_db()
    assert cadastro.preco == Decimal("450.00"), "o pedido nao muda o preco do cadastro"


@pytest.mark.django_db
def test_nome_ja_usado_por_outro_sku_nao_trava_a_importacao(conta):
    """O nome e unico na conta: sem o sufixo o pedido inteiro voltava com erro."""
    Servico.objects.create(nome="IMPER ATÉ 2,5M", sku="SERV-IMPER-ATE-25M")

    [servico] = vincular([_do_pedido()])

    novo = Servico.objects.get(sku="2432")
    assert novo.nome == "IMPER ATÉ 2,5M (2432)"
    assert servico["servico_id"] == novo.pk


@pytest.mark.django_db
def test_dois_itens_com_o_mesmo_sku_usam_um_cadastro_so(conta):
    primeiro, segundo = vincular([_do_pedido(), _do_pedido(item_id=8)])

    assert primeiro["servico_id"] == segundo["servico_id"]
    assert Servico.objects.count() == 1
