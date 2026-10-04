"""O cupom e identificado pelo nome dentro da conta; o codigo e interno e aleatorio."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.core.tenant.context import tenant_context
from apps.loja.models import Cupom

pytestmark = pytest.mark.django_db


def _cupom(nome, **campos):
    return Cupom.objects.create(name=nome, discount_type=Cupom.TipoDesconto.PERCENTUAL,
                                value=Decimal("10"), **campos)


def test_codigo_nasce_sozinho_aleatorio_e_diferente_por_cupom():
    """Sem codigo gerado, dois cupons sem codigo bateriam no indice (conta, codigo)."""
    primeiro, segundo = _cupom("Black Friday"), _cupom("Natal")

    assert len(primeiro.code) == 12 and primeiro.code.isalnum() and primeiro.code.isupper()
    assert primeiro.code != segundo.code


def test_nome_repetido_na_mesma_conta_e_recusado_pelo_banco():
    """O nome identifica o cupom: dois "Black Friday" na conta ninguem distingue."""
    _cupom("Black Friday")

    with pytest.raises(IntegrityError), transaction.atomic():
        _cupom("Black Friday")


def test_mesmo_nome_em_outra_conta_e_permitido(outra_conta):
    """Cada loja escolhe os nomes dela; o indice e por conta."""
    _cupom("Black Friday")
    with tenant_context(outra_conta):
        _cupom("Black Friday")

    assert Cupom.all_objects.filter(name="Black Friday").count() == 2


def test_cupom_aparece_pelo_nome():
    """O codigo e oculto: mostra-lo nas listas e selects confundiria o operador."""
    assert str(_cupom("Black Friday")) == "Black Friday"
