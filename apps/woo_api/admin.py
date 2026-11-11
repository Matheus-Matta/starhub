from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from apps.core.admin_base import TemaModelAdmin
from apps.core.json_widgets import TagsTema
from apps.core.tenant.context import get_current_account_id
from apps.woo_api.models import ChaveApi, ConfiguracaoFdc


class ConfiguracaoFdcForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoFdc
        fields = ["base_id_pedido"]

    def clean_base_id_pedido(self):
        # Vazio mantem a base: zerar sem querer mudaria o id de todos os pedidos para o ERP.
        valor = self.cleaned_data["base_id_pedido"]
        return self.instance.base_id_pedido if valor is None else valor


@admin.register(ConfiguracaoFdc)
class ConfiguracaoFdcAdmin(TemaModelAdmin):
    """Uma por conta: o menu abre direto a da conta ativa (criada se faltar)."""

    form = ConfiguracaoFdcForm
    relatorio = False
    fieldsets = [("Pedidos na API", {
        "fields": ["base_id_pedido"],
        "description": "O ERP da FDC le os pedidos pela API Woo do hub (/wp-json/wc/v3/"
                       "orders) com as chaves de API. O item sai sem o servico somado e o "
                       "total do pedido com ele: a FDC soma o servico do meta starhub.",
    })]

    def changelist_view(self, request, extra_context=None):
        obj, _ = ConfiguracaoFdc.objects.get_or_create(account_id=get_current_account_id())
        return HttpResponseRedirect(reverse("admin:woo_api_configuracaofdc_change",
                                            args=[obj.pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def response_change(self, request, obj):
        messages.success(request, "FDC Sistemas salvo.")
        return HttpResponseRedirect(request.path)


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
