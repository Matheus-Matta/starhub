"""Categorias de servico: no Suri cada uma vira um atributo da variacao, pela ordem."""

from django.contrib import admin

from apps.core.admin_base import TemaModelAdmin
from apps.loja.models import CategoriaServico


@admin.register(CategoriaServico)
class CategoriaServicoAdmin(TemaModelAdmin):
    list_display = ["nome", "ordem", "servicos_da_categoria", "updated_at"]
    search_fields = ["nome"]
    fields = [("nome", "ordem")]

    @admin.display(description="Servicos")
    def servicos_da_categoria(self, obj):
        return ", ".join(obj.servicos.values_list("nome", flat=True)) or "-"
