"""Roda uma tarefa de marketplace (sincronizar, webhooks, receber) e grava o andamento.

    def sincronizar(configuracao, progresso):
        progresso(3, 10, "Produtos: 3 de 10")
        return "10 itens encontrados."

    executar(execucao_id, sincronizar, canal="shopify", ambiente=ambiente_shopify)

`ambiente(configuracao)` e o contexto do marketplace em volta da funcao (loja atual,
coleta de avisos) e entrega a lista de avisos: aviso e item que falhou sem derrubar
a tarefa, e vira CONCLUIDA_COM_FALHAS. Erro que sobe da funcao vira FALHOU.
"""

import logging

from django.utils import timezone

from apps.core.origem import origem
from apps.core.tenant.context import tenant_context
from apps.integracoes.falhas import MAX_FALHAS, item, motivo_legivel
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.progresso import registrar
from apps.integracoes.tempo_real import publicar

ABERTAS = (ExecucaoIntegracao.Status.PENDENTE, ExecucaoIntegracao.Status.PROCESSANDO)

logger = logging.getLogger(__name__)


def gravar_aberta(execucao, **campos):
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


def _progresso(execucao):
    def progresso(processados, total, etapa):
        percentual = round(processados * 100 / total) if total else 0
        gravar_aberta(execucao, processados=processados, total=total,
                      progresso=percentual, etapa=etapa[:150])
        registrar(processados, total, etapa[:150])

    return progresso


def _concluir(execucao, mensagem, avisos):
    status = ExecucaoIntegracao.Status.CONCLUIDA
    if avisos:
        status = ExecucaoIntegracao.Status.CONCLUIDA_COM_FALHAS
        # O primeiro motivo fica no texto: a busca da lista de tarefas procura nele.
        mensagem = (f"{mensagem} {len(avisos)} com falha (primeira: {avisos[0]['motivo']}); "
                    "veja a lista de falhas nesta tarefa, corrija cada item na loja ou no "
                    "hub e sincronize de novo.")
    atual = ExecucaoIntegracao.objects.get(pk=execucao.pk)
    gravar_aberta(
        execucao, status=status, etapa=status.label, processados=atual.total,
        progresso=100, mensagem=mensagem[:4000], falhas=avisos[:MAX_FALHAS],
        concluida_em=timezone.now(),
    )
    return {"status": str(status), "message": mensagem}


def executar(execucao_id, funcao, *, canal, ambiente):
    execucao = ExecucaoIntegracao.all_objects.select_related("configuracao").get(pk=execucao_id)
    with tenant_context(execucao.account_id), origem(canal, via=execucao.configuracao.nome):
        # A liberada ja tem outra no lugar: reabri-la bateria no indice (uma por vez).
        comecou = gravar_aberta(
            execucao, status=ExecucaoIntegracao.Status.PROCESSANDO,
            etapa="Iniciando", iniciada_em=timezone.now(),
        )
        if not comecou:
            return {"status": "ignored", "message": "execucao ja encerrada"}
        avisos = []
        try:
            with ambiente(execucao.configuracao) as avisos:
                mensagem = funcao(execucao.configuracao, _progresso(execucao))
        except Exception as erro:  # a tarefa precisa persistir o erro antes de terminar
            # Um item que quebra derruba a sync inteira: FALHOU, com os avisos de antes
            # e o erro geral na tabela de falhas.
            geral = item("", motivo_legivel(erro))
            gravar_aberta(
                execucao, status=ExecucaoIntegracao.Status.FALHOU, etapa="Falhou",
                mensagem=str(erro)[:4000], falhas=[*avisos, geral][:MAX_FALHAS],
                concluida_em=timezone.now(),
            )
            return {"status": "failed", "message": str(erro)}
        return _concluir(execucao, mensagem, avisos)
