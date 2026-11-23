"""Botao de exportacao em toda listagem do tema, executado como tarefa."""

from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.urls import path, reverse

from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.retomar import colocar_na_fila

IGNORAR_NA_EXPORTACAO = {"p", "all", "_facets"}


def _nome_rota(model_admin):
    return f"{model_admin.opts.app_label}_{model_admin.opts.model_name}_exportar_relatorio"


def _query_sem_paginacao(request):
    query = request.GET.copy()
    for nome in IGNORAR_NA_EXPORTACAO:
        query.pop(nome, None)
    return query.urlencode()


class ExportarListaMixin:
    def get_urls(self):
        rota = path(
            "exportar-relatorio/",
            self.admin_site.admin_view(self.exportar_relatorio_view),
            name=_nome_rota(self),
        )
        return [rota, *super().get_urls()]

    def changelist_view(self, request, extra_context=None):
        contexto = dict(extra_context or {})
        if self.has_view_or_change_permission(request):
            url = reverse(f"admin:{_nome_rota(self)}")
            query = _query_sem_paginacao(request)
            contexto["url_exportar_lista"] = f"{url}?{query}" if query else url
        return super().changelist_view(request, contexto)

    def exportar_relatorio_view(self, request):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        # Reusa a validacao dos filtros do Django antes de criar uma tarefa invalida.
        self.get_changelist_instance(request)
        execucao = ExecucaoIntegracao.objects.create(
            tipo=ExecucaoIntegracao.Tipo.EXPORTAR_RELATORIO,
            parametros={
                "modelo": self.model._meta.label_lower,
                "query": _query_sem_paginacao(request),
                "usuario_id": request.user.pk,
            },
        )
        colocar_na_fila(
            execucao.pk, "apps.core.tasks.exportar_relatorio", (str(execucao.pk),)
        )
        return redirect(
            "admin:integracoes_execucaointegracao_change", execucao.pk
        )
