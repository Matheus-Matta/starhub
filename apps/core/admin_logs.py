"""Logs (django-auditlog) no admin: botao "Logs" na edicao de cada registro e a
lista "Entradas de log" filtrada so por ele.

O botao (templates/admin/change_form.html, url_logs) abre
/admin/auditlog/logentry/?registro=<content_type>-<pk>. O filtro "Registro" mostra
de quem sao os logs e da para limpar na gaveta. Mais recentes primeiro.

Conta: o log de model com conta guarda account_id em additional_data
(BaseModel.get_additional_data); usuario comum so ve os logs da conta dele.
Origem (admin, woo_api, shopify...): tambem no additional_data (apps/core/origem.py),
mostrada na coluna "usuario" e no filtro "origem".
"""

from urllib.parse import urlencode

from auditlog.admin import LogEntryAdmin
from auditlog.filters import CIDFilter, ResourceTypeFilter
from auditlog.models import LogEntry
from auditlog.registry import auditlog
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.urls import reverse
from django.utils.html import format_html

from apps.core import origem
from apps.core.models import Origin

PARAMETRO = "registro"


def url_logs(request, obj):
    """Lista de logs so deste registro; None sem permissao ou para model sem log."""
    if obj is None or obj.pk is None or not auditlog.contains(type(obj)):
        return None
    if not request.user.has_perm("auditlog.view_logentry"):
        return None
    tipo = ContentType.objects.get_for_model(type(obj))
    chave = f"{tipo.pk}-{obj.pk}"
    return f"{reverse('admin:auditlog_logentry_changelist')}?{urlencode({PARAMETRO: chave})}"


class RegistroFilter(admin.SimpleListFilter):
    """Logs de um registro so. Aparece na gaveta apenas quando aplicado (pelo botao)."""

    title = "registro"
    parameter_name = PARAMETRO

    def _partes(self):
        # pk pode ter "-" (UUID): so o primeiro separa o tipo.
        tipo, _, pk = (self.value() or "").partition("-")
        return (int(tipo), pk) if tipo.isdigit() and pk else (None, None)

    def lookups(self, request, model_admin):
        if self.value() is None:
            return []
        tipo, pk = self._partes()
        if tipo is None:
            # Sem opcao o Django ignora o filtro e listaria tudo: mostra vazio.
            return [(self.value(), "Registro invalido")]
        modelo = ContentType.objects.filter(pk=tipo).first()
        logs = model_admin.get_queryset(request)
        ultimo = logs.filter(content_type_id=tipo, object_pk=pk).first()
        nome = ultimo.object_repr if ultimo else f"#{pk}"
        return [(self.value(), f"{modelo.name.capitalize() if modelo else 'Registro'}: {nome}")]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset
        tipo, pk = self._partes()
        if tipo is None:
            return queryset.none()
        return queryset.filter(content_type_id=tipo, object_pk=pk)


def _coluna(metodo, rotulo):
    """Coluna do auditlog com o titulo em portugues (o pacote nao traz pt-BR)."""
    def coluna(self, obj):
        return metodo(self, obj)
    coluna.short_description = rotulo
    return coluna


class TipoFilter(ResourceTypeFilter):
    title = "tipo de registro"


class CorrelacaoFilter(CIDFilter):
    title = "id de correlacao"


ACOES = {
    LogEntry.Action.CREATE: "criacao", LogEntry.Action.UPDATE: "alteracao",
    LogEntry.Action.DELETE: "exclusao", LogEntry.Action.ACCESS: "acesso",
}


class AcaoFilter(admin.SimpleListFilter):
    title = "acao"
    parameter_name = "action"

    def lookups(self, request, model_admin):
        return [(str(valor), rotulo) for valor, rotulo in ACOES.items()]

    def queryset(self, request, queryset):
        return queryset.filter(action=self.value()) if self.value() else queryset


# Codigos gravados pelo apps/core/origem.py; integracoes usam os do Origin (shopify...).
ORIGENS = [origem.ADMIN, origem.WOO_API, *Origin.values, origem.SISTEMA]
TONS = {origem.ADMIN: "secondary", origem.SISTEMA: "secondary"}


class OrigemFilter(admin.SimpleListFilter):
    title = "origem"
    parameter_name = "origem"

    def lookups(self, request, model_admin):
        return [(codigo, codigo) for codigo in dict.fromkeys(ORIGENS)]

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        if self.value() == origem.SISTEMA:  # logs de antes da origem existir contam aqui
            return queryset.filter(
                Q(additional_data__origem=origem.SISTEMA) | Q(additional_data__origem__isnull=True)
            )
        return queryset.filter(additional_data__origem=self.value())


class LogsAdmin(LogEntryAdmin):
    list_display = ["created", "resource_url", "acao", "msg_short", "user_url", "cid_url"]
    list_filter = [RegistroFilter, OrigemFilter, AcaoFilter, TipoFilter, CorrelacaoFilter]
    ordering = ["-timestamp", "-id"]
    readonly_fields = ["created", "resource_url", "acao", "user_url", "msg"]
    fieldsets = [
        (None, {"fields": ["created", "user_url", "resource_url", "cid"]}),
        ("Alteracoes", {"fields": ["acao", "msg"]}),
    ]

    created = _coluna(LogEntryAdmin.created, "quando")
    resource_url = _coluna(LogEntryAdmin.resource_url, "registro")
    msg_short = _coluna(LogEntryAdmin.msg_short, "alteracoes")
    msg = _coluna(LogEntryAdmin.msg, "alteracoes")
    cid_url = _coluna(LogEntryAdmin.cid_url, "correlacao")

    @admin.display(description="usuario")
    def user_url(self, obj):
        """Quem fez e por onde: "admin" + usuario, "woo_api" + chave ou usuario do JWT."""
        dados = obj.additional_data or {}
        codigo = dados.get("origem") or origem.SISTEMA
        quem = LogEntryAdmin.user_url(self, obj) if obj.actor_id else dados.get("via", "")
        return format_html(
            '<span class="badge badge-{}">{}</span> {}', TONS.get(codigo, "primary"), codigo, quem
        )

    @admin.display(description="acao", ordering="action")
    def acao(self, obj):
        return ACOES.get(obj.action, obj.action)

    def get_queryset(self, request):
        logs = super().get_queryset(request)
        if request.user.is_superuser:
            return logs
        return logs.filter(additional_data__account_id=str(request.user.account_id))
