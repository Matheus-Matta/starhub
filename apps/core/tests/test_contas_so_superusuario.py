"""A pagina de Contas (lista e edicao) e so do superusuario."""

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.core.models import User

pytestmark = pytest.mark.django_db
LISTA = "admin:core_account_changelist"


@pytest.fixture
def operador(client, conta):
    """Staff com todas as permissoes de conta, mas sem ser superusuario."""
    usuario = User.objects.create_user("operador", "op@x.test", "senha-forte-123",
                                       account=conta, is_staff=True)
    usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="core",
                                                            codename__endswith="_account"))
    client.force_login(usuario)
    return client


def test_operador_nao_ve_contas_no_menu_nem_abre_a_pagina(operador, conta):
    """Antes, quem tinha a permissao de conta via a lista e editava a propria conta."""
    painel = operador.get(reverse("admin:index")).content.decode()

    assert reverse(LISTA) not in painel
    assert operador.get(reverse(LISTA)).status_code == 403
    assert operador.get(reverse("admin:core_account_change", args=[conta.pk])).status_code == 403


def test_superusuario_ve_e_abre_contas(admin_logado):
    assert reverse(LISTA) in admin_logado.get(reverse("admin:index")).content.decode()
    assert admin_logado.get(reverse(LISTA)).status_code == 200
