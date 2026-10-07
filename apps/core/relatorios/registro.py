"""Quais relatorios existem e quais a pessoa pode abrir.

Os genericos saem do admin (todo ModelAdmin do tema com `relatorio = True`); os
especiais vem de settings.STARHUB_RELATORIOS e aparecem primeiro no menu.
"""

from django.conf import settings
from django.contrib import admin
from django.utils.module_loading import import_string

from apps.core.admin_base import TemaMixin
from apps.core.relatorios.modelos import RelatorioModelo
from apps.core.ui.menu import ICONE_PADRAO, PREFIXO_MARCA


def _icone(model):
    icone = getattr(settings, "STARHUB_MENU_ICONES", {}).get(model._meta.label_lower, "")
    # Logo de plataforma nao cabe no submenu: fica o icone comum.
    return ICONE_PADRAO if not icone or icone.startswith(PREFIXO_MARCA) else icone


def _dos_admins():
    ordem = getattr(settings, "STARHUB_MENU_ORDEM", [])
    relatorios = [
        RelatorioModelo(model, model_admin, _icone(model))
        for model, model_admin in admin.site._registry.items()
        if isinstance(model_admin, TemaMixin) and model_admin.relatorio
    ]
    posicao = {rotulo: indice for indice, rotulo in enumerate(ordem)}
    return sorted(relatorios, key=lambda r: (
        posicao.get(r.model._meta.app_label, len(ordem)), str(r.titulo)))


def todos():
    especiais = [import_string(caminho)() for caminho in
                 getattr(settings, "STARHUB_RELATORIOS", [])]
    return [*especiais, *_dos_admins()]


def disponiveis(request):
    return [relatorio for relatorio in todos() if relatorio.permitido(request)]


def buscar(chave):
    return next((relatorio for relatorio in todos() if relatorio.chave == chave), None)
