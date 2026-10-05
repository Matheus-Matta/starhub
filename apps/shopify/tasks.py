from contextlib import contextmanager

from celery import shared_task

from apps.integracoes.execucao import executar
from apps.integracoes.models import ExecucaoIntegracao
from apps.shopify.contexto import coletando_avisos, usando_configuracao
from apps.shopify.frete_cadastro import cadastrar_frete
from apps.shopify.frete_diagnostico import verificar
from apps.shopify.sincronizar import cadastrar_webhooks, sincronizar_loja
from apps.shopify.webhooks import processar_webhook


@contextmanager
def _ambiente(configuracao):
    with usando_configuracao(configuracao), coletando_avisos() as avisos:
        yield avisos


def _executar(execucao_id, funcao):
    return executar(execucao_id, funcao, canal="shopify", ambiente=_ambiente)


@shared_task
def sincronizar_shopify(execucao_id):
    parametros = ExecucaoIntegracao.all_objects.filter(pk=execucao_id).values_list(
        "parametros", flat=True
    ).first() or {}
    recursos = parametros.get("recursos")
    if recursos is None:  # execucao sem escolha na tela: todos os permitidos
        return _executar(execucao_id, sincronizar_loja)

    def sincronizar(configuracao, progresso):
        return sincronizar_loja(configuracao, progresso, recursos=recursos)

    return _executar(execucao_id, sincronizar)


@shared_task
def cadastrar_webhooks_shopify(execucao_id):
    return _executar(execucao_id, cadastrar_webhooks)


@shared_task
def processar_webhook_shopify(execucao_id, recurso, operacao, dados):
    def processar(configuracao, progresso):
        return processar_webhook(configuracao, recurso, operacao, dados, progresso)

    return _executar(execucao_id, processar)


@shared_task
def cadastrar_frete_shopify(execucao_id):
    return _executar(execucao_id, cadastrar_frete)


@shared_task
def verificar_frete_shopify(execucao_id):
    return _executar(execucao_id, verificar)
