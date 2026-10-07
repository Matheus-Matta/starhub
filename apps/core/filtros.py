"""Filtro "Periodo" da listagem do admin: escolhe de/ate no calendario do tema.

    list_filter = [("created_at", FiltroPeriodo), "status"]

Usa ?created_at__date__gte=2026-09-01&created_at__date__lte=2026-09-30.
O __date compara so a data no fuso da loja: "ate 30/09" inclui o dia 30 inteiro.
"""

from django.contrib import admin
from django.utils.dateparse import parse_date


def ler_data(valor):
    if isinstance(valor, list):
        valor = valor[-1] if valor else ""
    try:
        return parse_date(valor or "")
    except ValueError:  # 2026-02-30: formato certo, data que nao existe
        return None


class FiltroPeriodo(admin.FieldListFilter):
    template = "admin/filtros/periodo.html"

    def __init__(self, field, request, params, model, model_admin, field_path):
        self.param_de = f"{field_path}__date__gte"
        self.param_ate = f"{field_path}__date__lte"
        super().__init__(field, request, params, model, model_admin, field_path)
        self.title = f"periodo ({self.title})"

    def expected_parameters(self):
        return [self.param_de, self.param_ate]

    def datas(self):
        return (ler_data(self.used_parameters.get(self.param_de)),
                ler_data(self.used_parameters.get(self.param_ate)))

    def queryset(self, request, queryset):
        de, ate = self.datas()
        filtros = {}
        if de:
            filtros[self.param_de] = de
        if ate:
            filtros[self.param_ate] = ate
        return queryset.filter(**filtros)

    def choices(self, changelist):
        de, ate = self.datas()
        nossos = {self.param_de, self.param_ate}
        yield {
            "de": de.isoformat() if de else "",
            "ate": ate.isoformat() if ate else "",
            # Outros filtros, busca e ordem continuam ao aplicar o periodo.
            "manter": [(nome, valor) for nome, valor in changelist.params.items()
                       if nome not in nossos],
            "limpar": changelist.get_query_string(remove=list(nossos)),
            "ativo": bool(de or ate),
        }
