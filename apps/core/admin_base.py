"""Base dos ModelAdmin do tema. Use no lugar de admin.ModelAdmin/TabularInline.

    @admin.register(Produto)
    class ProdutoAdmin(TemaModelAdmin):
        periodos = [("promocao_inicio", "promocao_fim")]  # vira seletor de periodo
        campos_json = {"tags": TagsTema(), "imagens": ImagensTema()}  # JSON pratico

O que ela faz: datas com o calendario do tema, booleano como switch, URL sem
esquema virando https, e tira o aviso "segure Ctrl para selecionar varios"
(o multi-select do tema nao usa Ctrl).
"""

import copy

from django.contrib import admin
from django.db import models

from apps.core import admin_condicoes, admin_lista_modal
from apps.core.admin_conta import ContaAdminMixin
from apps.core.json_widgets import campo_json, widget_padrao
from apps.core.ui import entradas
from apps.core.widgets import DataHoraTema, DataTema, SwitchTema, ligar_periodo

WIDGETS_TEMA = {
    models.DateField: {"widget": DataTema},
    models.DateTimeField: {"widget": DataHoraTema},
    models.BooleanField: {"widget": SwitchTema},
    models.URLField: {"assume_scheme": "https"},
}


class TemaMixin(ContaAdminMixin):
    formfield_overrides = WIDGETS_TEMA
    # Pares (campo_inicio, campo_fim) que abrem juntos no seletor de periodo.
    periodos = []
    # Campo JSON -> widget do tema (apps/core/json_widgets.py): tags, imagens,
    # metadados, listas e objetos deixam de ser JSON cru na tela. Sem declarar,
    # vale o widget_padrao (metadados e dicionarios); lista propria se declara.
    campos_json = {}
    # Colunas (de 12) de um campo na linha: {"postal_code": 3}. Padrao em
    # apps/core/ui/entradas.py; placeholder e mascara tambem vem de la.
    larguras = {}
    # Campo/secao/inline que so aparece conforme outro campo (apps/core/admin_condicoes.py).
    condicoes = {}

    def render_change_form(self, request, context, *args, **kwargs):
        context["condicoes_tela"] = admin_condicoes.para_tela(
            self, context.get("inline_admin_formsets", [])
        )
        return super().render_change_form(request, context, *args, **kwargs)

    def response_add(self, request, obj, *args, **kwargs):
        resposta = super().response_add(request, obj, *args, **kwargs)
        if admin_lista_modal.CAMPO_POST in request.POST:
            return admin_lista_modal.redirecionar_para_modal(request, resposta)
        return resposta

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        widget = self.campos_json.get(db_field.name)
        if widget is None and isinstance(db_field, models.JSONField):
            widget = widget_padrao(db_field)
        if widget is not None:
            kwargs.pop("widget", None)
            return campo_json(db_field, copy.deepcopy(widget), **kwargs)
        if entradas.form_class(db_field):
            kwargs.setdefault("form_class", entradas.form_class(db_field))
        campo = super().formfield_for_dbfield(db_field, request, **kwargs)
        if campo is not None:
            entradas.preparar(db_field, campo, self.larguras)
        for inicio, fim in self.periodos:
            if campo is not None and db_field.name == inicio:
                campo.widget = ligar_periodo(copy.deepcopy(campo.widget), fim)
        return campo

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        campo = super().formfield_for_manytomany(db_field, request, **kwargs)
        if campo is not None:
            # O admin acrescenta "Pressione Control... para selecionar mais de um"
            # ao help_text. Volta para o texto do proprio campo do model.
            campo.help_text = db_field.help_text
        return campo


class TemaModelAdmin(TemaMixin, admin.ModelAdmin):
    pass


class TemaTabularInline(TemaMixin, admin.TabularInline):
    pass


class TemaStackedInline(TemaMixin, admin.StackedInline):
    pass
