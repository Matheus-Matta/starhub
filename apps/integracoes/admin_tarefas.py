"""Tarefas no admin (integracoes e importacoes): lista com barra de progresso e tela
de acompanhamento.

A tela da tarefa aberta abre um WebSocket (/ws/tarefas/<id>/, consumers.py) e a barra
anda quando a tarefa grava andamento, sem a tela perguntar; ao terminar, a pagina
recarrega com o resultado do banco.
"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from apps.core.admin_base import TemaModelAdmin
from apps.core.admin_utils import badge
from apps.integracoes import progresso, retomar, sincronizacao, trafego
from apps.integracoes.admin_sincronizacao import falhas_legiveis, parametros_legiveis
from apps.integracoes.models import ExecucaoIntegracao

# Tarefas de planilha: a falha se corrige na planilha, nao na loja.
IMPORTACOES = (ExecucaoIntegracao.Tipo.IMPORTAR_AVALIACOES, ExecucaoIntegracao.Tipo.IMPORTAR_FRETE)
TONS = {"completed": "success", "completed_errors": "warning", "failed": "destructive",
        "running": "info"}


def duracao(execucao):
    """"2 min 05 s" entre o inicio e o fim; "" enquanto a tarefa nao terminou."""
    if not execucao.iniciada_em or not execucao.concluida_em:
        return ""
    segundos = int((execucao.concluida_em - execucao.iniciada_em).total_seconds())
    minutos, segundos = divmod(max(segundos, 0), 60)
    return f"{minutos} min {segundos:02d} s" if minutos else f"{segundos} s"


@admin.register(ExecucaoIntegracao)
class ExecucaoIntegracaoAdmin(TemaModelAdmin):
    change_form_template = "admin/integracoes/execucaointegracao/change_form.html"
    list_display = [
        "id_fmt", "created_at", "configuracao", "tipo", "status_fmt", "progresso_fmt", "etapa",
    ]
    list_display_links = ["id_fmt"]
    list_filter = ["status", "tipo", "configuracao__plataforma"]
    search_fields = ["configuracao__nome", "mensagem", "celery_task_id"]
    # JSON cru nunca aparece: a tela mostra parametros e falhas legiveis.
    exclude = ["falhas", "parametros"]
    readonly_fields = [
        "configuracao", "tipo", "status", "celery_task_id", "etapa", "processados", "total",
        "progresso", "mensagem", "iniciada_em", "concluida_em", "created_at", "updated_at",
    ]
    actions = ["retomar_falhas", "marcar_como_falhou"]

    def get_urls(self):
        rotas = [
            path("<path:object_id>/liberar/", self.admin_site.admin_view(self.liberar_view),
                 name="integracoes_execucaointegracao_liberar"),
            path("<path:object_id>/retomar/", self.admin_site.admin_view(self.retomar_view),
                 name="integracoes_execucaointegracao_retomar"),
        ]
        return [*rotas, *super().get_urls()]

    def _execucao(self, request, object_id):
        execucao = self.get_object(request, object_id)
        if execucao is None:
            raise Http404("Tarefa nao encontrada.")
        if not self.has_view_permission(request, execucao):
            raise PermissionDenied
        return execucao

    def liberar_view(self, request, object_id):
        return require_POST(self._liberar)(request, object_id)

    def _liberar(self, request, object_id):
        execucao = self._execucao(request, object_id)
        if not self.has_marcar_como_falhou_permission(request):
            raise PermissionDenied
        self.marcar_como_falhou(request, ExecucaoIntegracao.objects.filter(pk=execucao.pk))
        return HttpResponseRedirect(
            reverse("admin:integracoes_execucaointegracao_change", args=[execucao.pk]))

    def retomar_view(self, request, object_id):
        return require_POST(self._retomar)(request, object_id)

    def _retomar(self, request, object_id):
        execucao = self._execucao(request, object_id)
        if not self.has_marcar_como_falhou_permission(request):
            raise PermissionDenied
        self.retomar_falhas(request, ExecucaoIntegracao.objects.filter(pk=execucao.pk))
        return HttpResponseRedirect(
            reverse("admin:integracoes_execucaointegracao_change", args=[execucao.pk]))

    def get_search_results(self, request, queryset, search_term):
        # "779" e "#779" achar a tarefa: o operador copia o numero como aparece na lista.
        numero = search_term.strip().lstrip("#")
        if numero.isdigit():
            return queryset.filter(pk=int(numero)), False
        return super().get_search_results(request, queryset, search_term)

    def change_view(self, request, object_id, form_url="", extra_context=None):
        execucao = self.get_object(request, object_id)
        contexto = dict(extra_context or {})
        if execucao is not None:
            aberta = execucao.status in progresso.ABERTAS
            contexto.update({
                "title": f"Tarefa #{execucao.pk} - {execucao.get_tipo_display()}",
                "tom_status": TONS.get(execucao.status, "secondary"),
                "aberta": aberta,
                "url_progresso": f"/ws/tarefas/{execucao.pk}/" if aberta else "",
                "url_liberar": reverse("admin:integracoes_execucaointegracao_liberar",
                                       args=[execucao.pk]),
                "pode_liberar": aberta and self.has_marcar_como_falhou_permission(request),
                "url_retomar": reverse("admin:integracoes_execucaointegracao_retomar",
                                       args=[execucao.pk]),
                "pode_retomar": execucao.status in retomar.RETOMAVEIS
                and self.has_marcar_como_falhou_permission(request),
                "duracao": duracao(execucao),
                "parametros_html": parametros_legiveis(execucao),
                **trafego.para_tela(execucao.parametros),
                "falhas_html": falhas_legiveis(execucao) if execucao.falhas else "",
                "dica_falhas": (
                    "Corrija as linhas na planilha e importe de novo."
                    if execucao.tipo in IMPORTACOES
                    else "Corrija cada item na loja ou no hub e sincronize de novo."),
            })
        return super().change_view(request, object_id, form_url, contexto)

    def has_marcar_como_falhou_permission(self, request):
        # A pagina e somente leitura; quem libera uma travada e quem edita a integracao.
        return request.user.has_perm("integracoes.change_configuracaointegracao")

    @admin.action(description="Retomar as que falharam (coloca na fila de novo)",
                  permissions=["marcar_como_falhou"])
    def retomar_falhas(self, request, queryset):
        retomadas, recusas = 0, []
        for execucao in queryset.filter(status__in=retomar.RETOMAVEIS).order_by("pk"):
            try:
                retomar.retomar(execucao)
                retomadas += 1
            except retomar.NaoRetomavel as erro:
                recusas.append(str(erro))
        if retomadas:
            messages.success(request, f"{retomadas} tarefa(s) retomada(s); acompanhe o progresso.")
        for motivo in recusas[:5]:
            messages.warning(request, motivo)
        if len(recusas) > 5:
            messages.warning(request, f"E mais {len(recusas) - 5} que nao puderam ser retomadas.")
        if not retomadas and not recusas:
            messages.warning(request, "Nenhuma retomada: so tarefa que falhou pode voltar a fila.")

    @admin.action(description="Marcar como falhou (libera tarefa travada)",
                  permissions=["marcar_como_falhou"])
    def marcar_como_falhou(self, request, queryset):
        liberadas = sum(
            bool(sincronizacao.liberar_travada(execucao))
            for execucao in queryset.filter(status__in=sincronizacao.EM_ANDAMENTO)
        )
        if liberadas:
            messages.success(request, f"{liberadas} tarefa(s) marcada(s) como falhou.")
        else:
            messages.warning(
                request, "Nenhuma tarefa foi liberada: so pendente ou processando pode ser marcada."
            )

    @admin.display(description="#", ordering="id")
    def id_fmt(self, obj):
        return f"#{obj.pk}"

    @admin.display(description="progresso", ordering="progresso")
    def progresso_fmt(self, obj):
        return format_html(
            '<span class="tarefa-progresso-mini"><progress class="tarefa-barra tarefa-barra-{}" '
            'value="{}" max="100"></progress><span>{}%</span></span>',
            TONS.get(obj.status, "secondary"), obj.progresso, obj.progresso,
        )

    @admin.display(description="status", ordering="status")
    def status_fmt(self, obj):
        return badge(obj.get_status_display(), TONS.get(obj.status, "secondary"))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
