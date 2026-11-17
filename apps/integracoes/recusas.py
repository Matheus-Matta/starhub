"""Webhook recusado (assinatura errada, JSON quebrado) vira tarefa "Falhou" na tela de Tarefas.

Antes a recusa so ia para o log do servidor: o operador via o pedido faltando no hub e
nao tinha onde descobrir que a loja mandou e o hub recusou. A loja e conhecida (vem
na URL), entao a tarefa tem conta; webhook para loja inexistente (404) fica so no log.
"""

import logging

from django.utils import timezone

from apps.core.tenant.context import tenant_context
from apps.integracoes import trafego
from apps.integracoes.falhas import item
from apps.integracoes.models import ExecucaoIntegracao

logger = logging.getLogger(__name__)


def registrar_recusa(configuracao, request, status, motivo):
    agora = timezone.now()
    try:
        with tenant_context(configuracao.account_id):
            ExecucaoIntegracao.objects.create(
                configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.RECEBER,
                status=ExecucaoIntegracao.Status.FALHOU, etapa=f"Recusado (HTTP {status})",
                progresso=100, iniciada_em=agora, concluida_em=agora, mensagem=motivo[:4000],
                falhas=[item("", motivo)],
                parametros={"requisicao": trafego.requisicao(request, request.body),
                            "resposta": trafego.resposta(status)},
            )
    except Exception:  # registrar a recusa nunca troca a resposta que a loja recebe
        logger.exception("Nao registrou a recusa do webhook da configuracao %s", configuracao.pk)
