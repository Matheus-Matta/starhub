"""Retomar (rodar de novo) uma tarefa de integracao que falhou, na MESMA linha.

Cada tipo volta para a fila com o que precisa:

- Sincronizar / Exportar: os `parametros` do pedido (direcao e recursos).
- Cadastrar webhooks: so a configuracao.
- Importar avaliacoes / faixas de frete: o arquivo em parametros["arquivo"] (lido de novo).
- Enviar alteracao: parametros["reenvio"] = recurso, operacao e pk. As antigas,
  sem isso, sao lidas da mensagem ("produtos update 15: erro...").
- Receber webhook: parametros["reenvio"] com o corpo recebido. As antigas nao
  guardavam o corpo: nao tem o que reprocessar (a sincronizacao busca de novo).

A reabertura e um UPDATE filtrado pelo status: duas pessoas clicando ao mesmo tempo
nao colocam a tarefa duas vezes na fila. Sincronizacao reaberta com outra em
andamento bate no indice "uma por vez por loja" e e recusada.
"""

import logging
import re
from importlib import import_module

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.integracoes.models import ExecucaoIntegracao

Tipo, Status = ExecucaoIntegracao.Tipo, ExecucaoIntegracao.Status
RETOMAVEIS = (Status.FALHOU, Status.CONCLUIDA_COM_FALHAS)
TAREFAS = {
    Tipo.SINCRONIZAR: "apps.shopify.tasks.sincronizar_shopify",
    Tipo.EXPORTAR: "apps.integracoes.tasks.exportar_dados",
    Tipo.WEBHOOKS: "apps.shopify.tasks.cadastrar_webhooks_shopify",
    Tipo.RECEBER: "apps.shopify.tasks.processar_webhook_shopify",
    Tipo.ENVIAR: "apps.integracoes.tasks.enviar_alteracao",
    Tipo.IMPORTAR_AVALIACOES: "apps.loja.tasks.importar_avaliacoes",
    Tipo.IMPORTAR_FRETE: "apps.logistica.tasks.importar_faixas",
    Tipo.FRETE_CHECKOUT: "apps.shopify.tasks.cadastrar_frete_shopify",
    Tipo.VERIFICAR_FRETE: "apps.shopify.tasks.verificar_frete_shopify",
}
# Tarefa de marketplace que nao e a do Shopify (a de TAREFAS): troca pela da plataforma.
POR_PLATAFORMA = {
    "woocommerce": {
        Tipo.SINCRONIZAR: "apps.woocommerce.tasks.sincronizar_woocommerce",
        Tipo.WEBHOOKS: "apps.woocommerce.tasks.cadastrar_webhooks_woocommerce",
        Tipo.RECEBER: "apps.woocommerce.tasks.processar_webhook_woocommerce",
        Tipo.FRETE_CHECKOUT: "apps.woocommerce.tasks.frete_woocommerce",
    },
    "suri": {
        Tipo.SINCRONIZAR: "apps.suri.tasks.sincronizar_suri",
        Tipo.WEBHOOKS: "apps.suri.tasks.cadastrar_webhooks_suri",
        Tipo.RECEBER: "apps.suri.tasks.processar_webhook_suri",
    },
}
logger = logging.getLogger(__name__)
# "produtos update 15: motivo" e o comeco da mensagem de um envio que falhou.
ENVIO_NA_MENSAGEM = re.compile(r"^(\w+) (create|update|delete) (\S+):")


class NaoRetomavel(Exception):
    pass


def _reenvio(execucao):
    reenvio = (execucao.parametros or {}).get("reenvio")
    if reenvio:
        return reenvio
    achado = ENVIO_NA_MENSAGEM.match(execucao.mensagem or "")
    if execucao.tipo == Tipo.ENVIAR and achado:
        return dict(zip(("recurso", "operacao", "pk"), achado.groups(), strict=True))
    return None


def argumentos(execucao):
    """(caminho da tarefa, args) para colocar de novo na fila; NaoRetomavel se nao der."""
    if execucao.tipo not in TAREFAS:
        raise NaoRetomavel(f"#{execucao.pk}: este tipo de tarefa nao pode ser retomado.")
    plataforma = execucao.configuracao.plataforma if execucao.configuracao_id else ""
    caminho = POR_PLATAFORMA.get(plataforma, {}).get(execucao.tipo) or TAREFAS[execucao.tipo]
    identificador = str(execucao.pk)
    if execucao.tipo in (Tipo.SINCRONIZAR, Tipo.EXPORTAR, Tipo.WEBHOOKS, Tipo.IMPORTAR_AVALIACOES,
                         Tipo.IMPORTAR_FRETE, Tipo.FRETE_CHECKOUT, Tipo.VERIFICAR_FRETE):
        return caminho, (identificador,), {}
    reenvio = _reenvio(execucao)
    if reenvio is None:
        raise NaoRetomavel(
            f"#{execucao.pk}: a tarefa e de antes do Retomar e nao guardou os dados; "
            "use Sincronizar loja para buscar de novo."
        )
    if execucao.tipo == Tipo.RECEBER:
        args = (identificador, reenvio["recurso"], reenvio["operacao"], reenvio["dados"])
        return caminho, args, {}
    args = (str(execucao.configuracao_id), reenvio["recurso"], reenvio["operacao"],
            reenvio["pk"])
    return caminho, args, {"execucao_id": identificador}


def retomar(execucao):
    """Reabre a tarefa como Pendente e coloca na fila depois do commit."""
    caminho, args, kwargs = argumentos(execucao)
    try:
        with transaction.atomic():
            reaberta = ExecucaoIntegracao.all_objects.filter(
                pk=execucao.pk, status__in=RETOMAVEIS
            ).update(
                status=Status.PENDENTE, etapa="Retomada, aguardando na fila", progresso=0,
                processados=0, total=0, mensagem="", falhas=[], iniciada_em=None,
                concluida_em=None, celery_task_id="", updated_at=timezone.now(),
            )
    except IntegrityError as erro:
        raise NaoRetomavel(
            f"#{execucao.pk}: ja existe outra sincronizacao desta loja na fila ou rodando; "
            "espere ela terminar."
        ) from erro
    if not reaberta:
        raise NaoRetomavel(f"#{execucao.pk}: so tarefa que falhou pode ser retomada.")
    transaction.on_commit(lambda: colocar_na_fila(execucao.pk, caminho, args, kwargs))


def colocar_na_fila(execucao_id, caminho, args=None, kwargs=None):
    """Enfileira a tarefa; Celery fora do ar devolve a execucao para Falhou com o motivo."""
    from apps.core.tarefas import enfileirar

    modulo, nome = caminho.rsplit(".", 1)
    try:
        tarefa = getattr(import_module(modulo), nome)
        resultado = enfileirar(tarefa, *(args or ()), **(kwargs or {}))
    except Exception as erro:  # broker fora: a tarefa nao pode ficar Pendente para sempre
        logger.exception("Falha ao enfileirar a tarefa %s", execucao_id)
        ExecucaoIntegracao.all_objects.filter(pk=execucao_id, status=Status.PENDENTE).update(
            status=Status.FALHOU, etapa="Falhou", concluida_em=timezone.now(),
            mensagem=f"Nao foi possivel colocar na fila ({erro}). Confira o Redis/Celery "
            "e retome de novo.",
        )
        return
    ExecucaoIntegracao.all_objects.filter(pk=execucao_id).update(
        celery_task_id=resultado.id or "")
