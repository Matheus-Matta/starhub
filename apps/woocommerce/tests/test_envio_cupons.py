"""Regras canonicas do cupom enviadas para a API do WooCommerce."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.loja.models import Cupom
from apps.woocommerce.cliente import WooErro
from apps.woocommerce.envio.cadastros import CupomWoo
from apps.woocommerce.importar_cupons import importar_cupom

pytestmark = pytest.mark.django_db


def test_woocommerce_recebe_faixa_minima_e_maxima_do_pedido():
    cupom = Cupom.objects.create(
        name="Faixa", code="FAIXA", discount_type=Cupom.TipoDesconto.PERCENTUAL,
        value=10, minimum_requirement=Cupom.RequisitoMinimo.SUBTOTAL,
        minimum_subtotal=Decimal("100"), subtotal_maximo=Decimal("500"),
    )
    enviador = CupomWoo(SimpleNamespace(configuracao=None))

    corpo = enviador.corpo(cupom, criando=True)

    assert corpo["minimum_amount"] == "100.00"
    assert corpo["maximum_amount"] == "500.00"


def test_importacao_traz_codigo_e_subtotal_maximo_para_o_hub():
    cupom, criado = importar_cupom({
        "id": 7, "code": "ATE500", "discount_type": "percent", "amount": "10",
        "minimum_amount": "100", "maximum_amount": "500", "status": "publish",
    })

    assert criado
    assert cupom.code == "ATE500"
    assert cupom.minimum_subtotal == Decimal("100.00")
    assert cupom.subtotal_maximo == Decimal("500.00")


def test_importacao_atualiza_codigo_aleatorio_de_cupom_ja_existente():
    Cupom.objects.create(
        name="ATE500", code="CODIGOANTIGO",
        discount_type=Cupom.TipoDesconto.PERCENTUAL, value=10,
    )

    cupom, criado = importar_cupom({
        "id": 8, "code": "ATE500", "discount_type": "percent", "amount": "10",
    })

    assert not criado
    assert cupom.code == "ATE500"


def test_woocommerce_recusa_regra_avancada_em_vez_de_ignorar():
    cupom = Cupom.objects.create(
        name="Noturno", code="NOITE", discount_type=Cupom.TipoDesconto.PERCENTUAL,
        value=10, dias_semana=["5", "6"],
    )

    with pytest.raises(WooErro, match="dias da semana"):
        CupomWoo(SimpleNamespace(configuracao=None)).corpo(cupom, criando=True)
