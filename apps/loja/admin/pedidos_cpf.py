"""Acoes do Shopify na lista de pedidos: "Buscar CPF" e "Reimportar do Shopify".

Os pedidos que vieram do Shopify antes da busca do documento chegaram sem CPF; os
gravados errado por versao antiga (ex.: sem itens) voltam com a reimportacao.
As acoes so criam a tarefa: a consulta a Shopify roda no worker (ExecucaoIntegracao,
com barra, falhas e Retomar), nunca dentro da requisicao do admin.
"""

from django.contrib import admin, messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.core.models import Origin
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.integracoes.retomar import colocar_na_fila

TAREFA = "apps.shopify.tasks.preencher_cpf_shopify"
TAREFA_REIMPORTAR = "apps.shopify.tasks.reimportar_pedidos_shopify"


@admin.action(description="Buscar CPF no Shopify (segundo plano)", permissions=["change"])
def buscar_cpf_no_shopify(modeladmin, request, queryset):
    ids = list(queryset.filter(origin=Origin.SHOPIFY, active=True).exclude(
        endereco_cobranca__document__gt="").order_by("pk").values_list("pk", flat=True))
    if not ids:
        messages.warning(request, "Nenhum pedido selecionado e do Shopify sem CPF: "
                                  "nao ha o que buscar.")
        return None
    return _enfileirar(request, ExecucaoIntegracao.Tipo.CPF_PEDIDOS, TAREFA, ids,
                       f"Busca do CPF de {len(ids)} pedido(s) enviada para a fila.")


@admin.action(description="Reimportar do Shopify (segundo plano)", permissions=["change"])
def reimportar_do_shopify(modeladmin, request, queryset):
    ids = list(queryset.filter(origin=Origin.SHOPIFY, active=True).order_by("pk")
               .values_list("pk", flat=True))
    if not ids:
        messages.warning(request, "Nenhum pedido selecionado e do Shopify (e ativo): nao ha "
                                  "o que reimportar.")
        return None
    return _enfileirar(request, ExecucaoIntegracao.Tipo.REIMPORTAR_PEDIDOS, TAREFA_REIMPORTAR,
                       ids, f"Reimportacao de {len(ids)} pedido(s) enviada para a fila.")


def _enfileirar(request, tipo, tarefa, ids, aviso):
    configuracao = ConfiguracaoIntegracao.objects.filter(
        plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY, active=True).first()
    if configuracao is None:
        messages.error(request, "Nenhuma loja Shopify ativa nesta conta: configure em "
                                "Integracoes > Shopify e salve.")
        return None
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=configuracao, tipo=tipo, etapa="Na fila", parametros={"pedidos": ids})
    transaction.on_commit(lambda: colocar_na_fila(execucao.pk, tarefa, (str(execucao.pk),)))
    messages.success(request, aviso)
    return HttpResponseRedirect(
        reverse("admin:integracoes_execucaointegracao_change", args=[execucao.pk]))
