"""A migration 0009 leva o dado do Shopify do cupom para o vinculo e sabe voltar."""

import importlib

import pytest
from django.apps import apps as apps_reais

from apps.core.models import ExternalReference
from apps.loja.models import Cupom

pytestmark = pytest.mark.django_db
migracao = importlib.import_module("apps.loja.migrations.0009_cupom_shopify_no_vinculo")
GID = "gid://shopify/DiscountCodeNode/9"


def cupom(**campos):
    return Cupom.objects.create(name="Promo", discount_type=Cupom.TipoDesconto.PERCENTUAL,
                                value=10, **campos)


def test_dado_do_shopify_sai_do_cupom_e_vai_para_o_vinculo():
    """Sem a migration o cupom ficaria com dado de marketplace e o vinculo sem o tipo."""
    c = cupom(metadata={"shopify": {"id": GID, "tipo": "DiscountCodeBasic"}, "outro": 1})
    ref = ExternalReference.objects.create(platform="shopify", entity_type="cupons",
                                           external_id=GID, object_id=str(c.pk))
    migracao.para_o_vinculo(apps_reais, None)
    c.refresh_from_db()
    ref.refresh_from_db()
    assert c.metadata == {"outro": 1}
    assert ref.metadata["tipo"] == "DiscountCodeBasic"


def test_cupom_sem_vinculo_ganha_o_vinculo_pelo_gid_guardado():
    c = cupom(metadata={"shopify": {"id": GID, "status": "ACTIVE"}})
    migracao.para_o_vinculo(apps_reais, None)
    ref = ExternalReference.objects.get(entity_type="cupons", external_id=GID)
    assert ref.object_id == str(c.pk) and ref.metadata["status"] == "ACTIVE"
    assert "shopify" not in Cupom.objects.get(pk=c.pk).metadata


def test_reverso_devolve_o_dado_ao_cupom():
    c = cupom()
    ExternalReference.objects.create(platform="shopify", entity_type="cupons", external_id=GID,
                                     object_id=str(c.pk), metadata={"status": "EXPIRED"})
    migracao.para_o_cupom(apps_reais, None)
    assert Cupom.objects.get(pk=c.pk).metadata == {"shopify": {"status": "EXPIRED"}}
