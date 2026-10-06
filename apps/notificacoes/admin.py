"""Telas: E-mail (SMTP) e Notificacoes (uma de cada por conta) e as notificacoes recebidas.

As duas configuracoes nao tem lista: o menu abre direto a da conta ativa (criada se
faltar). Notificacoes recebidas: so as do proprio usuario; o sino do cabecalho leva ate la.
"""

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.core.admin_base import TemaModelAdmin
from apps.core.tarefas import enfileirar
from apps.core.tenant.context import get_current_account_id
from apps.notificacoes import contas
from apps.notificacoes.forms import ConfiguracaoEmailForm, ConfiguracaoNotificacaoForm, linhas
from apps.notificacoes.models import ConfiguracaoEmail, ConfiguracaoNotificacao, Notificacao


class _UmaPorConta(TemaModelAdmin):
    def changelist_view(self, request, extra_context=None):
        email, notificacao = contas.garantir(get_current_account_id())
        obj = email if self.model is ConfiguracaoEmail else notificacao
        opcoes = self.model._meta
        return HttpResponseRedirect(reverse(
            f"admin:{opcoes.app_label}_{opcoes.model_name}_change", args=[obj.pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def response_change(self, request, obj):
        return HttpResponseRedirect(request.path)


@admin.register(ConfiguracaoEmail)
class ConfiguracaoEmailAdmin(_UmaPorConta):
    form = ConfiguracaoEmailForm
    fieldsets = [
        ("Servidor", {"fields": [("host", "porta"), "seguranca", ("usuario", "senha")]}),
        ("Remetente", {"fields": [("remetente_email", "remetente_nome")]}),
        ("Teste", {"fields": ["testar"]}),
    ]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not form.cleaned_data.get("testar"):
            messages.success(request, "E-mail (SMTP) salvo.")
            return
        para = request.user.email or obj.remetente_email
        if not para:
            messages.warning(request, "Salvo. Para testar, ponha um e-mail no seu perfil.")
            return
        from apps.notificacoes.tasks import testar_email

        enfileirar(testar_email, str(obj.account_id), request.user.pk, para)
        messages.success(request, f"Salvo. E-mail de teste para {para} foi para a fila; "
                                  "o resultado chega no sino do cabecalho.")


@admin.register(ConfiguracaoNotificacao)
class ConfiguracaoNotificacaoAdmin(_UmaPorConta):
    form = ConfiguracaoNotificacaoForm

    def get_fieldsets(self, request, obj=None):
        return [("Geral", {"fields": ["ligado", "destinatarios"]}),
                *[(grupo, {"fields": campos}) for grupo, campos in linhas()]]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        messages.success(request, "Notificacoes salvas.")


@admin.register(Notificacao)
class NotificacaoAdmin(TemaModelAdmin):
    list_display = ["titulo", "mensagem", "lida", "created_at"]
    list_filter = ["lida", "evento"]
    search_fields = ["titulo", "mensagem"]
    actions = ["marcar_lidas"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(usuario=request.user)

    def has_module_permission(self, request):
        return False  # fora do menu: o sino do cabecalho e a porta de entrada

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description="Marcar como lidas")
    def marcar_lidas(self, request, queryset):
        quantas = queryset.filter(lida=False).update(lida=True)
        messages.success(request, f"{quantas} marcada(s) como lida(s).")
