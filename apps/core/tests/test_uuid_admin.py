"""O uuid aparece so na tela de detalhe, somente leitura; nunca na lista nem no "adicionar".

Editavel, o operador trocaria o identificador estavel do registro; na lista, so ocupa
coluna. ModelAdmin com fieldsets nao mostra campo fora deles: o uuid entra no primeiro.
"""

import pytest
from django.contrib import admin
from django.test import RequestFactory

from apps.core.admin_base import TemaModelAdmin
from apps.core.models import ExternalReference


class ComFieldsets(TemaModelAdmin):
    fieldsets = [("Dados", {"fields": ["platform", "external_id"]}),
                 ("Outros", {"fields": ["object_id"]})]


class SemFieldsets(TemaModelAdmin):
    fields = ["platform", "external_id"]


def _admin(classe):
    return classe(ExternalReference, admin.site)


def _campos(modelo_admin, obj, usuario):
    return [c for _, opcoes in modelo_admin.get_fieldsets(_pedido(usuario), obj)
            for c in opcoes["fields"]]


def _pedido(usuario):
    pedido = RequestFactory().get("/")
    pedido.user = usuario
    return pedido


@pytest.mark.django_db
@pytest.mark.parametrize("classe", [ComFieldsets, SemFieldsets])
def test_uuid_so_no_detalhe_e_somente_leitura(classe, conta, admin_user):
    obj = ExternalReference.objects.create(platform="shopify", entity_type="produtos",
                                           object_id="1", external_id="gid://1")
    modelo_admin = _admin(classe)

    assert "uuid" in _campos(modelo_admin, obj, admin_user)
    assert "uuid" in modelo_admin.get_readonly_fields(_pedido(admin_user), obj)
    assert "uuid" not in _campos(modelo_admin, None, admin_user)
    assert "uuid" not in modelo_admin.get_list_display(_pedido(admin_user))

