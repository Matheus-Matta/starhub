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

from django import forms
from django.contrib import admin
from django.db import models

from apps.core import admin_condicoes, admin_lista_modal, admin_logs
from apps.core.admin_conta import ContaAdminMixin
from apps.core.fields import TextoHTMLField
from apps.core.json_widgets import campo_json, widget_padrao
from apps.core.ui import entradas
from apps.core.widgets import DataHoraTema, DataTema, EditorHTML, SwitchTema, ligar_periodo

WIDGETS_TEMA = {
    TextoHTMLField: {"widget": EditorHTML},
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
    # Chave estrangeira que so mostra o "+" (sem lapis/olho/x): numa linha de lista os
    # quatro icones ao lado do select apertam a tabela.
    relacao_so_adicionar = []
    # FK para o pai quando o form abre no modal da lista dele (admin_lista_modal):
    # "produto" na variante. Nesse modal o campo fica oculto, o pai ja esta decidido.
    pai_da_lista = None

    def render_change_form(self, request, context, *args, **kwargs):
        context["condicoes_tela"] = admin_condicoes.para_tela(
            self, context.get("inline_admin_formsets", [])
        )
        context["url_logs"] = admin_logs.url_logs(request, kwargs.get("obj"))
        return super().render_change_form(request, context, *args, **kwargs)

    def response_add(self, request, obj, *args, **kwargs):
        resposta = super().response_add(request, obj, *args, **kwargs)
        if admin_lista_modal.CAMPO_POST in request.POST:
            return admin_lista_modal.redirecionar_para_modal(request, resposta)
        return resposta

    def response_change(self, request, obj):
        # Clique no "+" com o form alterado: salvou e volta abrindo o modal.
        resposta = super().response_change(request, obj)
        if admin_lista_modal.CAMPO_POST in request.POST:
            return admin_lista_modal.redirecionar_para_modal(request, resposta)
        return resposta

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        pai = self.pai_da_lista
        if admin_lista_modal.aberto_pelo_pai(self, request, obj) and pai in form.base_fields:
            form.base_fields[pai].widget = forms.HiddenInput()
        return form

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
        if campo is not None and db_field.name in self.relacao_so_adicionar:
            campo.widget.can_change_related = campo.widget.can_view_related = False
            campo.widget.can_delete_related = False
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


def _tem_uuid(modelo):
    return any(campo.name == "uuid" for campo in modelo._meta.concrete_fields)


class TemaModelAdmin(TemaMixin, admin.ModelAdmin):
    # O uuid (BaseModel) so aparece no detalhe e so para leitura: no "adicionar" ele
    # ainda nao existe e na lista ocuparia coluna sem uso para o operador.
    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        if obj is not None and _tem_uuid(self.model) and "uuid" not in campos:
            campos.append("uuid")
        return campos

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        mostrados = {c for _, opcoes in fieldsets for c in opcoes.get("fields", ())}
        if obj is None or not _tem_uuid(self.model) or "uuid" in mostrados or not fieldsets:
            return fieldsets
        # Lista nova, sem alterar a declarada na classe (a mesma em toda requisicao).
        # Para o superusuario a primeira secao e "Conta" (admin_conta): fica junto da origem.
        nome, opcoes = fieldsets[0]
        return [(nome, {**opcoes, "fields": [*opcoes["fields"], "uuid"]}), *fieldsets[1:]]


class TemaTabularInline(TemaMixin, admin.TabularInline):
    # Toda lista de filhos com a mesma cara (titulo + "Adicionar", tabela encostada,
    # lixeira que tira a linha na hora): templates/admin/edit_inline/lista.html.
    template = "admin/edit_inline/lista.html"


class TemaStackedInline(TemaMixin, admin.StackedInline):
    pass
