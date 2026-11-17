"""Tarefas x registros no admin: o filtro do botao "Tarefas" e o card "Registros afetados".

O filtro e o mesmo da lista de logs (apps/core/admin_registro_filtro.py): produto
inclui variantes, midias e vinculos com as lojas; aqui ele procura em TarefaRegistro.
"""

from django.urls import NoReverseMatch, reverse
from django.utils.http import urlencode

from apps.core import registros
from apps.core.admin_registro_filtro import RegistroFilter
from apps.integracoes.modelos_registro import TarefaRegistro

LIMITE_TELA = 200


class RegistroDaTarefaFilter(RegistroFilter):
    def filtrar(self, queryset, alvo):
        ligadas = TarefaRegistro.objects.filter(registros.filtro(alvo)).values("execucao_id")
        return queryset.filter(pk__in=ligadas)


def _url_edicao(ligacao):
    tipo = ligacao.content_type
    try:
        return reverse(f"admin:{tipo.app_label}_{tipo.model}_change", args=[ligacao.object_pk])
    except NoReverseMatch:  # model sem tela no admin (ex.: valor da variante)
        return ""


def contexto(request, execucao):
    ligacoes = execucao.registros.select_related("content_type")
    linhas = [{"tipo": str(ligacao.content_type.name).capitalize(),
               "descricao": ligacao.descricao or f"#{ligacao.object_pk}",
               "id": ligacao.object_pk, "url": _url_edicao(ligacao)}
              for ligacao in ligacoes[:LIMITE_TELA]]
    url_logs = ""
    if request.user.has_perm("auditlog.view_logentry"):
        url_logs = (f"{reverse('admin:auditlog_logentry_changelist')}?"
                    f"{urlencode({'cid': f'tarefa-{execucao.pk}'})}")
    return {"registros_tarefa": linhas, "total_registros": ligacoes.count(),
            "url_logs_tarefa": url_logs}
