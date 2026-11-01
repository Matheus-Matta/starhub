"""Acoes "Desativar pedidos" e "Reativar pedidos" na lista de pedidos.

Desativado, o pedido sai de toda integracao (ver services/pedidos_ativos.py). A acao
so cria a tarefa: o lote roda no worker (barra, falhas e Retomar na tela de Tarefas),
para uma selecao de milhares de pedidos nao segurar a requisicao do admin.
"""

from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.retomar import colocar_na_fila

TAREFA = "apps.loja.tasks.ativar_pedidos"


def _enfileirar(request, queryset, ativo):
    # So quem precisa mudar: o resto ja esta no estado pedido.
    ids = list(queryset.filter(active=not ativo).order_by("pk").values_list("pk", flat=True))
    estado = "ativo(s)" if ativo else "desativado(s)"
    if not ids:
        messages.warning(request, f"Nenhum pedido mudou: todos os selecionados ja estao {estado}.")
        return None
    execucao = ExecucaoIntegracao.objects.create(
        tipo=ExecucaoIntegracao.Tipo.ATIVAR_PEDIDOS, etapa="Na fila",
        parametros={"pedidos": ids, "ativo": ativo})
    transaction.on_commit(lambda: colocar_na_fila(execucao.pk, TAREFA, (str(execucao.pk),)))
    acao = "Reativacao" if ativo else "Desativacao"
    messages.success(request, f"{acao} de {len(ids)} pedido(s) enviada para a fila.")
    return HttpResponseRedirect(
        reverse("admin:integracoes_execucaointegracao_change", args=[execucao.pk]))


@admin.action(description="Desativar pedidos (sai de todas as integracoes)",
              permissions=["change"])
def desativar_pedidos(modeladmin, request, queryset):
    return _enfileirar(request, queryset, ativo=False)


@admin.action(description="Reativar pedidos", permissions=["change"])
def reativar_pedidos(modeladmin, request, queryset):
    return _enfileirar(request, queryset, ativo=True)
