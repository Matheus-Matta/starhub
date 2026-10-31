"""Acao "Buscar CPF no Shopify" na lista de pedidos.

Os pedidos que vieram do Shopify antes da busca do documento chegaram sem CPF.
A acao so cria a tarefa: a consulta a Shopify roda no worker (ExecucaoIntegracao,
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


@admin.action(description="Buscar CPF no Shopify (segundo plano)", permissions=["change"])
def buscar_cpf_no_shopify(modeladmin, request, queryset):
    ids = list(queryset.filter(origin=Origin.SHOPIFY).exclude(
        endereco_cobranca__document__gt="").order_by("pk").values_list("pk", flat=True))
    if not ids:
        messages.warning(request, "Nenhum pedido selecionado e do Shopify sem CPF: "
                                  "nao ha o que buscar.")
        return None
    configuracao = ConfiguracaoIntegracao.objects.filter(
        plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY, active=True).first()
    if configuracao is None:
        messages.error(request, "Nenhuma loja Shopify ativa nesta conta: configure em "
                                "Integracoes > Shopify e salve.")
        return None
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.CPF_PEDIDOS,
        etapa="Na fila", parametros={"pedidos": ids})
    transaction.on_commit(lambda: colocar_na_fila(execucao.pk, TAREFA, (str(execucao.pk),)))
    messages.success(request, f"Busca do CPF de {len(ids)} pedido(s) enviada para a fila.")
    return HttpResponseRedirect(
        reverse("admin:integracoes_execucaointegracao_change", args=[execucao.pk]))
