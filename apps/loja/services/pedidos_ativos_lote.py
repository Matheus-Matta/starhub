"""Desativar ou reativar pedidos em lote, no worker (tarefa "Desativar/reativar pedidos").

A acao da lista grava parametros {"pedidos": [ids], "ativo": False} e enfileira;
aqui roda um por um, em ordem de id (o lock de cada linha nao cruza com outro lote),
com barra, falhas por pedido e Retomar. Rodar de novo e seguro: quem ja esta no
estado pedido e so contado.
"""

import logging

from django.utils import timezone

from apps.core.origem import origem
from apps.core.tenant.context import tenant_context
from apps.integracoes.falhas import MAX_FALHAS, item, motivo_legivel
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.progresso import registrar
from apps.integracoes.tasks import ABERTAS
from apps.integracoes.tasks import _gravar as gravar
from apps.loja.models import Pedido
from apps.loja.services.pedidos_ativos import mudar_ativo

Status = ExecucaoIntegracao.Status
AVISAR_A_CADA = 20  # pedidos entre um aviso de progresso e outro (banco + WebSocket)
logger = logging.getLogger(__name__)


def _verbo(ativo):
    return "reativado(s)" if ativo else "desativado(s)"


def _aplicar(execucao, ids, ativo):
    mudaram, falhas = 0, []
    for posicao, pk in enumerate(ids, start=1):
        try:
            mudaram += mudar_ativo(pk, ativo)
        except Pedido.DoesNotExist:
            falhas.append(item("pedidos", "O pedido foi excluido antes da tarefa rodar.", pk))
        except Exception as erro:  # um pedido ruim nao para o lote
            logger.exception("Pedido %s na tarefa %s", pk, execucao.pk)
            falhas.append(item("pedidos", motivo_legivel(erro), pk))
        if posicao % AVISAR_A_CADA == 0 or posicao == len(ids):
            etapa = f"Pedido {posicao} de {len(ids)}"
            gravar(execucao, processados=posicao, total=len(ids),
                   progresso=round(posicao * 100 / len(ids)), etapa=etapa)
            registrar(posicao, len(ids), etapa)
    return mudaram, falhas


def executar(execucao_id):
    execucao = ExecucaoIntegracao.all_objects.select_related("created_by").get(pk=execucao_id)
    parametros = execucao.parametros or {}
    ids, ativo = sorted(parametros.get("pedidos") or []), bool(parametros.get("ativo"))
    # O operador que pediu fica como autor da alteracao no historico de cada pedido.
    with tenant_context(execucao.account_id, execucao.created_by), origem(
            "admin", via=f"tarefa #{execucao.pk}"):
        comecou = ExecucaoIntegracao.all_objects.filter(pk=execucao.pk, status__in=ABERTAS).update(
            status=Status.PROCESSANDO, etapa="Iniciando", iniciada_em=timezone.now(),
            updated_at=timezone.now())
        if not comecou:
            return {"status": "ignored", "message": "execucao ja encerrada"}
        mudaram, falhas = _aplicar(execucao, ids, ativo)
        mensagem = (f"{len(ids)} pedido(s): {mudaram} {_verbo(ativo)}, "
                    f"{len(ids) - mudaram - len(falhas)} ja estava(m) assim, "
                    f"{len(falhas)} com erro.")
        if falhas:
            mensagem += " Veja a lista de falhas e use Retomar para tentar de novo."
        status = Status.CONCLUIDA_COM_FALHAS if falhas else Status.CONCLUIDA
        gravar(execucao, status=status, etapa=status.label, progresso=100,
               processados=len(ids), total=len(ids), mensagem=mensagem,
               falhas=falhas[:MAX_FALHAS], concluida_em=timezone.now())
        return {"status": str(status), "message": mensagem}
