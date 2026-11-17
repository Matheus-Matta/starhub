"""Estado da tarefa de envio (aberta, concluida, falhou), gravado sem save().

Separado de tasks.py pelo limite de tamanho; tasks.py reexporta os nomes, e
importar_planilha usa o `_gravar` daqui pelo mesmo motivo do envio.
"""

import logging

from django.utils import timezone

from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.tempo_real import publicar

ABERTAS = (ExecucaoIntegracao.Status.PENDENTE, ExecucaoIntegracao.Status.PROCESSANDO)

logger = logging.getLogger(__name__)


def _gravar(execucao, **campos):
    # QuerySet.update() nao aplica auto_now: updated_at e o sinal de vida que a
    # sincronizacao usa para liberar uma execucao cujo worker morreu. So grava na
    # aberta: a liberada nao volta a andar nem troca o FALHOU por CONCLUIDA.
    gravou = ExecucaoIntegracao.all_objects.filter(pk=execucao.pk, status__in=ABERTAS).update(
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


def _abrir(configuracao, execucao_id, etapa, reenvio):
    if execucao_id:
        execucao = ExecucaoIntegracao.all_objects.filter(pk=execucao_id).first()
        if execucao:
            return execucao
    return ExecucaoIntegracao.objects.create(
        configuracao=configuracao,
        tipo=ExecucaoIntegracao.Tipo.ENVIAR,
        status=ExecucaoIntegracao.Status.PROCESSANDO,
        etapa=etapa[:150],
        total=1,
        iniciada_em=timezone.now(),
        # O que o botao Retomar precisa para mandar de novo (apps/integracoes/retomar.py).
        parametros={"reenvio": reenvio},
    )


def _concluir(execucao, etapa, mensagem):
    _gravar(
        execucao, status=ExecucaoIntegracao.Status.CONCLUIDA, processados=1, progresso=100,
        etapa="Concluida", mensagem=f"{etapa}: {mensagem}"[:4000], concluida_em=timezone.now(),
    )


def _falhar(execucao, etapa, erro):
    _gravar(
        execucao, status=ExecucaoIntegracao.Status.FALHOU, etapa="Falhou",
        mensagem=f"{etapa}: {erro}"[:4000], concluida_em=timezone.now(),
    )
