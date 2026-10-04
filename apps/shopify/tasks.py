import logging

from celery import shared_task
from django.utils import timezone

from apps.core.origem import origem
from apps.core.tenant.context import tenant_context
from apps.integracoes.falhas import MAX_FALHAS, item, motivo_legivel
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.progresso import registrar
from apps.integracoes.tempo_real import publicar
from apps.shopify.contexto import coletando_avisos, usando_configuracao
from apps.shopify.frete_cadastro import cadastrar_frete
from apps.shopify.frete_diagnostico import verificar
from apps.shopify.sincronizar import cadastrar_webhooks, sincronizar_loja
from apps.shopify.webhooks import processar_webhook

ABERTAS = (ExecucaoIntegracao.Status.PENDENTE, ExecucaoIntegracao.Status.PROCESSANDO)

logger = logging.getLogger(__name__)


def _gravar_aberta(execucao, **campos):
    # So na aberta: a liberada por falta de sinal (sincronizacao.liberar_travada) nao
    # volta a mostrar progresso nem troca o FALHOU por CONCLUIDA. QuerySet.update()
    # nao aplica auto_now, e updated_at e o sinal de vida da execucao.
    gravou = ExecucaoIntegracao.objects.filter(pk=execucao.pk, status__in=ABERTAS).update(
        updated_at=timezone.now(), **campos
    )
    if gravou:
        publicar(execucao.pk)
    if not gravou and "status" in campos:
        logger.warning(
            "Execucao %s ja estava encerrada (liberada por falta de sinal?); "
            "resultado nao gravado: %s", execucao.pk, campos.get("mensagem", ""),
        )
    return gravou


def _executar(execucao_id, funcao):
    execucao = ExecucaoIntegracao.all_objects.select_related("configuracao").get(pk=execucao_id)
    conta_id = execucao.account_id
    with tenant_context(conta_id), origem("shopify", via=execucao.configuracao.nome):
        # A liberada ja tem outra no lugar: reabri-la bateria no indice (uma por vez).
        comecou = _gravar_aberta(
            execucao, status=ExecucaoIntegracao.Status.PROCESSANDO,
            etapa="Iniciando", iniciada_em=timezone.now(),
        )
        if not comecou:
            return {"status": "ignored", "message": "execucao ja encerrada"}

        def progresso(processados, total, etapa):
            percentual = round(processados * 100 / total) if total else 0
            _gravar_aberta(
                execucao, processados=processados, total=total,
                progresso=percentual, etapa=etapa[:150],
            )
            registrar(processados, total, etapa[:150])

        avisos = []
        try:
            with usando_configuracao(execucao.configuracao), coletando_avisos() as avisos:
                mensagem = funcao(execucao.configuracao, progresso)
        except Exception as erro:  # a tarefa precisa persistir o erro antes de terminar
            # Um item que quebra derruba a sync inteira (sincronizar.py): FALHOU, com os
            # avisos de antes e o erro geral na tabela de falhas.
            geral = item("", motivo_legivel(erro))
            _gravar_aberta(
                execucao, status=ExecucaoIntegracao.Status.FALHOU, etapa="Falhou",
                mensagem=str(erro)[:4000], falhas=[*avisos, geral][:MAX_FALHAS],
                concluida_em=timezone.now(),
            )
            return {"status": "failed", "message": str(erro)}
        status = ExecucaoIntegracao.Status.CONCLUIDA
        if avisos:
            status = ExecucaoIntegracao.Status.CONCLUIDA_COM_FALHAS
            # O primeiro motivo fica no texto: a busca da lista de tarefas procura nele.
            mensagem = (f"{mensagem} {len(avisos)} com falha (primeira: {avisos[0]['motivo']}); "
                        "veja a lista de falhas nesta tarefa, corrija cada item na loja ou no "
                        "hub e sincronize de novo.")
        atual = ExecucaoIntegracao.objects.get(pk=execucao.pk)
        _gravar_aberta(
            execucao, status=status, etapa=status.label, processados=atual.total,
            progresso=100, mensagem=mensagem[:4000], falhas=avisos[:MAX_FALHAS],
            concluida_em=timezone.now(),
        )
        return {"status": str(status), "message": mensagem}


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
