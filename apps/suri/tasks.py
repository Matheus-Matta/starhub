from celery import shared_task

from apps.integracoes.execucao import executar
from apps.integracoes.models import ExecucaoIntegracao
from apps.suri.contexto import ambiente
from apps.suri.sincronizar import sincronizar_loja
from apps.suri.webhooks import cadastrar_webhooks, processar_webhook


def _executar(execucao_id, funcao):
    return executar(execucao_id, funcao, canal="suri", ambiente=ambiente)


@shared_task
def sincronizar_suri(execucao_id):
    parametros = ExecucaoIntegracao.all_objects.filter(pk=execucao_id).values_list(
        "parametros", flat=True).first() or {}
    recursos = parametros.get("recursos")  # None: todos os permitidos

    def sincronizar(configuracao, progresso):
        return sincronizar_loja(configuracao, progresso, recursos=recursos)

    return _executar(execucao_id, sincronizar)


@shared_task
def cadastrar_webhooks_suri(execucao_id):
    return _executar(execucao_id, cadastrar_webhooks)


@shared_task
def processar_webhook_suri(execucao_id, recurso, operacao, dados):
    """Mesma assinatura das outras plataformas (o Retomar chama igual); `dados` = {"id"}."""
    def processar(configuracao, progresso):
        return processar_webhook(configuracao, dados["id"], progresso)

    return _executar(execucao_id, processar)
