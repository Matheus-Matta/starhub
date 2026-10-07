from django.contrib import admin

from apps.core.admin_base import TemaModelAdmin
from apps.loja.models import Servico


@admin.register(Servico)
class ServicoAdmin(TemaModelAdmin):
    # Servico nasce sozinho no pedido (SKU SERV-<NOME>); aqui o operador troca o SKU
    # pelo codigo do ERP. O id e o do hub e nao muda.
    list_display = ["nome", "sku", "active", "updated_at"]
    search_fields = ["nome", "sku"]
    list_filter = ["active"]
    fields = ["nome", "sku", "active"]
