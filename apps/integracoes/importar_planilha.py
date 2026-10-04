"""Tarefa generica de importar planilha: le o arquivo, importa linha por linha e mostra.

Quem usa (avaliacoes, faixas de frete) so da a regra de UMA linha:

    def importar_linha(dados) -> (objeto, criado)   # ou levanta LinhaInvalida("motivo")

e chama `executar(execucao_id, importar_linha, objeto="faixas", quem=...)` na sua
shared_task. O resto e igual para todos: o arquivo gravado no MEDIA
(parametros["arquivo"]), a barra pelo WebSocket, as falhas por linha ("Linha 7:
motivo"), o resumo e o status (Concluida / Concluida com falhas / Falhou). Uma linha
ruim nunca para as outras.
"""

import logging

from django.core.files.storage import default_storage
from django.utils import timezone

from apps.core import planilha
from apps.core.origem import origem
from apps.core.tenant.context import tenant_context
from apps.integracoes.falhas import MAX_FALHAS, item
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.progresso import registrar
from apps.integracoes.tasks import ABERTAS
from apps.integracoes.tasks import _gravar as gravar

Status = ExecucaoIntegracao.Status
AVISAR_A_CADA = 10  # linhas entre um aviso de progresso e outro (banco + WebSocket)
logger = logging.getLogger(__name__)


class LinhaInvalida(Exception):
    """Motivo para o operador corrigir a linha na planilha."""


def _linhas(execucao):
    caminho = (execucao.parametros or {}).get("arquivo", "")
    if not caminho or not default_storage.exists(caminho):
        raise planilha.PlanilhaInvalida("O arquivo da planilha nao existe mais; envie de novo.")
    with default_storage.open(caminho, "rb") as arquivo:
        return planilha.ler(arquivo.read(), caminho)


def _importar(execucao, linhas, importar_linha, recurso, quem):
    criadas = atualizadas = 0
    falhas = []
    for posicao, (numero, dados) in enumerate(linhas, start=1):
        try:
            _, criada = importar_linha(dados)
            criadas += int(criada)
            atualizadas += int(not criada)
        except LinhaInvalida as erro:
            falhas.append(item(recurso, f"Linha {numero}: {erro}", "", quem(dados)))
        except Exception as erro:  # erro inesperado numa linha nao derruba as outras
            logger.exception("Linha %s da planilha da tarefa %s", numero, execucao.pk)
            falhas.append(item(recurso, f"Linha {numero}: {erro}", "", quem(dados)))
        if posicao % AVISAR_A_CADA == 0 or posicao == len(linhas):
            etapa = f"Linha {posicao} de {len(linhas)}"
            gravar(execucao, processados=posicao, total=len(linhas),
                   progresso=round(posicao * 100 / len(linhas)), etapa=etapa)
            registrar(posicao, len(linhas), etapa)
    return criadas, atualizadas, falhas


def executar(execucao_id, importar_linha, *, objeto, recurso, quem, preparar=None):
    """Roda a importacao da execucao. `preparar(execucao, linhas)` roda antes das linhas."""
    execucao = ExecucaoIntegracao.all_objects.select_related("created_by").get(pk=execucao_id)
    nome = (execucao.parametros or {}).get("nome", "planilha")
    with tenant_context(execucao.account_id), origem("importacao", via=nome):
        comecou = ExecucaoIntegracao.all_objects.filter(pk=execucao.pk, status__in=ABERTAS).update(
            status=Status.PROCESSANDO, etapa="Lendo a planilha", iniciada_em=timezone.now(),
            updated_at=timezone.now())
        if not comecou:
            return {"status": "ignored", "message": "execucao ja encerrada"}
        try:
            linhas = _linhas(execucao)
        except planilha.PlanilhaInvalida as erro:
            gravar(execucao, status=Status.FALHOU, etapa="Falhou", mensagem=str(erro),
                   concluida_em=timezone.now())
            return {"status": "failed", "message": str(erro)}
        if preparar:
            preparar(execucao, linhas)
        criadas, atualizadas, falhas = _importar(execucao, linhas, importar_linha, recurso, quem)
        mensagem = (f"{len(linhas)} linhas: {criadas} {objeto} criadas, "
                    f"{atualizadas} atualizadas, {len(falhas)} com erro.")
        if falhas:
            mensagem += " Corrija as linhas da lista de falhas na planilha e importe de novo."
        status = Status.CONCLUIDA_COM_FALHAS if falhas else Status.CONCLUIDA
        gravar(execucao, status=status, etapa=status.label, progresso=100,
               processados=len(linhas), total=len(linhas), mensagem=mensagem,
               falhas=falhas[:MAX_FALHAS], concluida_em=timezone.now())
        return {"status": str(status), "message": mensagem}
