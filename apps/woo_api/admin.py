from django.contrib import admin, messages
from django.utils.html import format_html

from apps.core.admin_base import TemaModelAdmin
from apps.core.json_widgets import TagsTema
from apps.woo_api.models import ChaveApi


@admin.register(ChaveApi)
class ChaveApiAdmin(TemaModelAdmin):
    campos_json = {"scopes": TagsTema(simples=True)}
    list_display = ["descricao", "permissao", "final", "last_used_at", "expires_at", "active"]
    list_filter = ["permissao", "active"]
    search_fields = ["descricao", "final_chave"]
    fields = ["descricao", "permissao", "scopes", "expires_at", "active", "final",
              "last_used_at", "created_at"]
    readonly_fields = ["final", "last_used_at", "created_at"]

    @admin.display(description="chave")
    def final(self, obj):
        return f"ck_...{obj.final_chave}" if obj.final_chave else "gerada ao salvar"

    def save_model(self, request, obj, form, change):
        chave = segredo = None
        if not change:
            chave, segredo = obj.gerar()
        super().save_model(request, obj, form, change)
        if chave:
            # Unica vez que a chave aparece inteira: o banco so guarda o hash.
            messages.warning(
                request,
                format_html(
                    "Copie agora, ela nao sera mostrada de novo.<br>"
                    "Consumer key: <code>{}</code><br>Consumer secret: <code>{}</code>",
                    chave,
                    segredo,
                ),
            )
