"""Conferencia dos pedidos das lojas pelo beat: a cada 30 min e quando o beat sobe.

Webhook perdido (loja, hub ou rede fora) deixava o pedido fora do hub ate alguem
sincronizar a mao. Aqui cada loja ativa com Receber > Pedidos > Buscar ganha uma
sincronizacao so de pedidos, limitada a janela de criacao/alteracao abaixo. Ela usa
o mesmo caminho do botao Sincronizar loja (tarefa em Tarefas, uma por vez por loja,
importador que casa pelo id externo e pelo SKU, cria o que falta e atualiza o resto).

Janela: inicio = onde a ultima conferencia concluida parou - 5 min; na primeira, o
ultimo pedido que entrou da loja - 5 min (sem nenhum, o ultimo dia). Fim = agora +
5 min. O inicio NAO e o ultimo pedido recebido depois da primeira vez: o pedido A
perdido as 10:00 ficaria de fora para sempre se o B chegasse bem as 10:20.
"""

import logging
from datetime import UTC, datetime, timedelta

from celery import shared_task
from django.db.models import Max
from django.utils import timezone

from apps.core.models import ExternalReference
from apps.core.tenant.context import tenant_context
from apps.integracoes import sincronizacao
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao

MARGEM = timedelta(minutes=5)
SEM_HISTORICO = timedelta(days=1)
CONCLUIDAS = (ExecucaoIntegracao.Status.CONCLUIDA,
              ExecucaoIntegracao.Status.CONCLUIDA_COM_FALHAS)

logger = logging.getLogger(__name__)


def _ultima_conferencia(configuracao):
    parametros = (ExecucaoIntegracao.all_objects
                  .filter(configuracao_id=configuracao.pk, status__in=CONCLUIDAS,
                          tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR,
                          parametros__has_key="janela")
                  .order_by("-created_at").values_list("parametros", flat=True).first())
    return datetime.fromisoformat(parametros["janela"]["conferido_ate"]) if parametros else None


def _ultimo_pedido(configuracao):
    return ExternalReference.all_objects.filter(
        account_id=configuracao.account_id, platform=configuracao.plataforma,
        entity_type="pedidos").aggregate(ultimo=Max("created_at"))["ultimo"]


def janela(configuracao, agora):
    base = (_ultima_conferencia(configuracao) or _ultimo_pedido(configuracao)
            or agora - SEM_HISTORICO)
    return {"inicio": (base - MARGEM).astimezone(UTC).isoformat(),
            "fim": (agora + MARGEM).astimezone(UTC).isoformat(),
            "conferido_ate": agora.astimezone(UTC).isoformat()}


def limites(dados):
    """(inicio, fim) da janela gravada nos parametros, em UTC."""
    return (datetime.fromisoformat(dados["inicio"]).astimezone(UTC),
            datetime.fromisoformat(dados["fim"]).astimezone(UTC))


def conferir_lojas(agora=None):
    """Agenda a conferencia de cada loja que pode; devolve as tarefas criadas."""
    agora = agora or timezone.now()
    criadas = []
    lojas = ConfiguracaoIntegracao.all_objects.filter(
        active=True, plataforma__in=list(sincronizacao.IMPORTADORES)).order_by("pk")
    for configuracao in lojas:
        if not configuracao.habilitado("receber", "pedidos", "get"):
            continue
        try:
            with tenant_context(configuracao.account_id):
                criadas.append(sincronizacao.iniciar(
                    configuracao, sincronizacao.IMPORTAR, ["pedidos"],
                    janela=janela(configuracao, agora)))
        except sincronizacao.SincronizacaoEmAndamento:
            # A que esta rodando ja traz os pedidos; a proxima conferencia cobre o resto.
            logger.info("Conferencia de pedidos pulada: loja %s ja sincronizando.",
                        configuracao.pk)
        except ValueError as erro:
            logger.warning("Conferencia de pedidos da loja %s nao agendada: %s",
                           configuracao.pk, erro)
    logger.info("Conferencia de pedidos: %s loja(s) agendada(s).", len(criadas))
    return criadas


@shared_task
def conferir_pedidos_das_lojas():
    return len(conferir_lojas())
