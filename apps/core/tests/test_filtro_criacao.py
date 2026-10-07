"""Toda lista do tema filtra por periodo da data de criacao, sem cada admin declarar."""

from datetime import datetime

import pytest
from django.contrib import admin
from django.urls import reverse
from django.utils import timezone

from apps.core.admin_base import TemaMixin
from apps.core.filtros import FiltroPeriodo
from apps.loja.models import Tag

pytestmark = pytest.mark.django_db

# Configuracao unica por conta: a "lista" redireciona direto para o formulario.
SEM_LISTA = {"integracoes.ConfiguracaoIntegracao", "notificacoes.ConfiguracaoEmail",
             "notificacoes.ConfiguracaoNotificacao"}
ADMINS_DO_TEMA = sorted(
    modelo._meta.label for modelo, model_admin in admin.site._registry.items()
    if isinstance(model_admin, TemaMixin) and modelo._meta.label not in SEM_LISTA
)


def _lista(cliente, label, query=""):
    app, modelo = label.lower().split(".")
    return cliente.get(reverse(f"admin:{app}_{modelo}_changelist") + query)


def _periodos(resposta):
    return [spec for spec in resposta.context["cl"].filter_specs
            if isinstance(spec, FiltroPeriodo)]


@pytest.mark.parametrize("label", ADMINS_DO_TEMA)
def test_toda_lista_do_tema_tem_um_filtro_de_periodo_da_criacao(admin_logado, label):
    """Antes so pedido, produto, cliente e avaliacao tinham; o resto obrigava a rolar a lista."""
    resposta = _lista(admin_logado, label)

    assert resposta.status_code == 200
    periodos = _periodos(resposta)
    assert len(periodos) == 1
    assert periodos[0].field_path in ("created_at", "date_joined")


def test_filtro_de_criacao_restringe_a_lista_de_tags(admin_logado):
    antiga, nova = Tag.objects.create(nome="Antiga"), Tag.objects.create(nome="Nova")
    Tag.objects.filter(pk=antiga.pk).update(
        created_at=timezone.make_aware(datetime(2026, 1, 10, 12)))
    Tag.objects.filter(pk=nova.pk).update(
        created_at=timezone.make_aware(datetime(2026, 9, 10, 12)))

    resposta = _lista(admin_logado, "loja.Tag", "?created_at__date__gte=2026-09-01")

    assert list(resposta.context["cl"].queryset) == [nova]
