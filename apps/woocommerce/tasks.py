from celery import shared_task

from apps.integracoes.execucao import executar
from apps.integracoes.models import ExecucaoIntegracao
from apps.woocommerce.contexto import ambiente
from apps.woocommerce.frete_envio import enviar_frete, remover_frete
from apps.woocommerce.sincronizar import sincronizar_loja
from apps.woocommerce.webhooks import processar_webhook
from apps.woocommerce.webhooks_cadastro import cadastrar_webhooks


def _executar(execucao_id, funcao):
    return executar(execucao_id, funcao, canal="woocommerce", ambiente=ambiente)


@shared_task
def sincronizar_woocommerce(execucao_id):
    parametros = ExecucaoIntegracao.all_objects.filter(pk=execucao_id).values_list(
        "parametros", flat=True).first() or {}
    recursos = parametros.get("recursos")  # None: todos os permitidos

    def sincronizar(configuracao, progresso):
        return sincronizar_loja(configuracao, progresso, recursos=recursos)

    return _executar(execucao_id, sincronizar)


@shared_task
def cadastrar_webhooks_woocommerce(execucao_id):
    return _executar(execucao_id, cadastrar_webhooks)


@shared_task
def processar_webhook_woocommerce(execucao_id, recurso, operacao, dados):
    def processar(configuracao, progresso):
        return processar_webhook(configuracao, recurso, operacao, dados, progresso)

    return _executar(execucao_id, processar)


@shared_task
def frete_woocommerce(execucao_id):
    """Liga (envia as zonas) ou desliga (parametros["remover"]) o frete do hub na loja."""
    remover = (ExecucaoIntegracao.all_objects.filter(pk=execucao_id).values_list(
        "parametros", flat=True).first() or {}).get("remover")
    return _executar(execucao_id, remover_frete if remover else enviar_frete)
