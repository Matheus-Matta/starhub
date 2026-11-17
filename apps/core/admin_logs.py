"""Logs (django-auditlog) no admin: botoes "Logs" e "Tarefas" na edicao de cada registro
e a lista "Entradas de log" filtrada por ele (e pelo que pertence a ele).

O botao (templates/admin/change_form.html, url_logs) abre
/admin/auditlog/logentry/?registro=<content_type>-<pk>; o filtro e o de
apps/core/admin_registro_filtro.py, que inclui variantes, midias, itens e vinculos.
Mais recentes primeiro. A tela de um log (log_detalhe.py) diz quem, por onde, a
requisicao, a tarefa e o que mudou com o rotulo do campo.

Conta: o log de model com conta guarda account_id em additional_data
(BaseModel.get_additional_data); usuario comum so ve os logs da conta dele.
Origem (admin, woo_api, shopify...): tambem no additional_data (apps/core/origem.py),
mostrada na coluna "usuario" e no filtro "origem".
"""

from auditlog.admin import LogEntryAdmin
from auditlog.filters import CIDFilter, ResourceTypeFilter
from auditlog.registry import auditlog
from django.contrib import admin
from django.db.models import Q
from django.utils.html import format_html

from apps.core import log_detalhe, origem
from apps.core.admin_registro_filtro import RegistroFilter, url_lista
from apps.core.log_detalhe import ACOES, TONS_ORIGEM
from apps.core.models import Origin


def url_logs(request, obj):
    """Lista de logs deste registro; None sem permissao ou para model sem log."""
    if obj is None or not auditlog.contains(type(obj)):
        return None
    return url_lista(request, obj, "admin:auditlog_logentry_changelist",
                     "auditlog.view_logentry")


def url_tarefas(request, obj):
    """Lista de tarefas que tocaram este registro (ou o que pertence a ele)."""
    return url_lista(request, obj, "admin:integracoes_execucaointegracao_changelist",
                     "integracoes.view_execucaointegracao")


class TipoFilter(ResourceTypeFilter):
    title = "tipo de registro"


class CorrelacaoFilter(CIDFilter):
    title = "requisicao ou tarefa"


class AcaoFilter(admin.SimpleListFilter):
    title = "acao"
    parameter_name = "action"

    def lookups(self, request, model_admin):
        return [(str(valor), rotulo) for valor, rotulo in ACOES.items()]

    def queryset(self, request, queryset):
        return queryset.filter(action=self.value()) if self.value() else queryset


# Codigos gravados pelo apps/core/origem.py; integracoes usam os do Origin (shopify...).
ORIGENS = [origem.ADMIN, origem.WOO_API, *Origin.values, "importacao", origem.SISTEMA]


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
    change_form_template = "admin/auditlog/logentry/change_form.html"
    list_display = ["quando", "registro", "acao", "campos", "usuario", "tarefa"]
    list_display_links = ["quando"]
    list_filter = [RegistroFilter, OrigemFilter, AcaoFilter, TipoFilter, CorrelacaoFilter]
    list_select_related = ["actor", "content_type"]
    ordering = ["-timestamp", "-id"]

    @admin.display(description="quando", ordering="timestamp")
    def quando(self, obj):
        return obj.timestamp.strftime("%d/%m/%Y %H:%M:%S")

    @admin.display(description="registro")
    def registro(self, obj):
        tipo = str(obj.content_type.name).capitalize() if obj.content_type_id else ""
        return format_html('<span class="table-identity-meta">{}</span> {}', tipo, obj.object_repr)

    @admin.display(description="o que mudou")
    def campos(self, obj):
        return log_detalhe.campos_alterados(obj)

    @admin.display(description="usuario")
    def usuario(self, obj):
        """Quem fez e por onde: "admin" + usuario, "woo_api" + chave ou usuario do JWT."""
        dados = obj.additional_data or {}
        codigo = dados.get("origem") or origem.SISTEMA
        nome, _ = log_detalhe.autor(obj)
        quem = " - ".join(filter(None, [nome, dados.get("via", "")]))
        return format_html('<span class="badge badge-{}">{}</span> {}',
                           TONS_ORIGEM.get(codigo, "primary"), codigo, quem)

    @admin.display(description="tarefa")
    def tarefa(self, obj):
        tarefa_id = (obj.additional_data or {}).get("tarefa_id")
        return f"#{tarefa_id}" if tarefa_id else "-"

    @admin.display(description="acao", ordering="action")
    def acao(self, obj):
        return ACOES.get(obj.action, obj.action)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        log = self.get_object(request, object_id)
        contexto = dict(extra_context or {})
        if log is not None:
            contexto.update(log_detalhe.contexto(log))
            contexto["title"] = f"{log.object_repr} - {ACOES.get(log.action, log.action)}"
        return super().change_view(request, object_id, form_url, contexto)

    def get_queryset(self, request):
        logs = super().get_queryset(request)
        if request.user.is_superuser:
            return logs
        return logs.filter(additional_data__account_id=str(request.user.account_id))
