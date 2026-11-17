"""Filtro "registro" das listas de Logs e de Tarefas, aberto pelos botoes da edicao.

    /admin/auditlog/logentry/?registro=12-345                 # produto 345 e o que e dele
    /admin/integracoes/execucaointegracao/?registro=so:12-345  # so o produto

Aparece na gaveta so quando aplicado, com as duas opcoes (com ou sem os itens
relacionados) para o operador trocar. Quem decide os relacionados: apps/core/registros.py.
"""

from urllib.parse import urlencode

from django.contrib import admin
from django.urls import NoReverseMatch, reverse

from apps.core import registros

PARAMETRO = "registro"


def url_lista(request, obj, rota, permissao):
    """Lista `rota` filtrada por `obj`; None sem permissao, sem pk ou sem a rota."""
    if obj is None or obj.pk is None or not request.user.has_perm(permissao):
        return None
    try:
        lista = reverse(rota)
    except NoReverseMatch:
        return None
    return f"{lista}?{urlencode({PARAMETRO: registros.chave(obj)})}"


class RegistroFilter(admin.SimpleListFilter):
    title = "registro"
    parameter_name = PARAMETRO
    campo_tipo = "content_type_id"
    campo_pk = "object_pk"

    def lookups(self, request, model_admin):
        valor = self.value()
        if valor is None:
            return []
        tipo, _, _ = registros.separar(valor)
        if tipo is None:
            # Sem opcao o Django ignora o filtro e listaria tudo: mostra vazio.
            return [(valor, "Registro invalido")]
        base = valor.removeprefix(registros.SO)
        nome = registros.nome(base)
        return [(base, f"{nome} e itens relacionados"), (registros.SO + base, f"Somente {nome}")]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset
        alvo = registros.alvo(self.value())
        return self.filtrar(queryset, alvo) if alvo else queryset.none()

    def filtrar(self, queryset, alvo):
        return queryset.filter(registros.filtro(alvo, self.campo_tipo, self.campo_pk))
