"""Tarefas orfas no dev: o servidor parou com elas rodando.

No dev (STARHUB_TAREFAS_EM_THREAD) a tarefa roda numa thread DENTRO do runserver.
Parar ou reiniciar o servidor (Ctrl+C, arquivo salvo) mata a thread sem aviso, e a
tarefa ficava "Processando" para sempre. Aqui elas viram Falhou, com o motivo, e
podem ser retomadas (apps/integracoes/retomar.py).

Dois ganchos, porque um so nao basta:
- atexit: o servidor parando (Ctrl+C, reinicio do autoreload).
- primeira requisicao: o que o atexit nao pega (processo morto a forca). Nenhuma
  tarefa deste processo existe ainda nesse momento: todas nascem de requisicoes.

Em prod nada disso liga: o worker do Celery e outro processo, e parar o Daphne nao
mata tarefa nenhuma.
"""

import atexit
import logging
import os
import sys

from django.conf import settings
from django.core.signals import request_started
from django.utils import timezone

logger = logging.getLogger(__name__)
PAROU = "O servidor parou durante a tarefa. Use Retomar para rodar de novo."
REINICIOU = "O servidor reiniciou e a tarefa ficou pela metade. Use Retomar para rodar de novo."


def marcar_orfas(motivo):
    """Abertas viram Falhou; devolve quantas."""
    from apps.integracoes.models import ExecucaoIntegracao

    Status = ExecucaoIntegracao.Status
    agora = timezone.now()
    return ExecucaoIntegracao.all_objects.filter(
        status__in=(Status.PENDENTE, Status.PROCESSANDO)
    ).update(status=Status.FALHOU, etapa="Falhou", mensagem=motivo, concluida_em=agora,
             updated_at=agora)


def _ao_parar():
    try:
        marcadas = marcar_orfas(PAROU)
    except Exception:  # banco ja fechado no fim do processo: o gancho de subida pega
        logger.warning("Nao foi possivel marcar as tarefas orfas ao parar", exc_info=True)
        return
    if marcadas:
        print(f"StarHub: {marcadas} tarefa(s) em andamento marcada(s) como Falhou.")


def _na_primeira_requisicao(**_kwargs):
    request_started.disconnect(_na_primeira_requisicao, dispatch_uid="starhub-orfas")
    marcadas = marcar_orfas(REINICIOU)
    if marcadas:
        logger.warning("%s tarefa(s) orfa(s) de antes do reinicio marcada(s) como Falhou",
                       marcadas)


def servindo_no_dev():
    """True so no processo do runserver que atende (nao no vigia do autoreload)."""
    if not getattr(settings, "STARHUB_TAREFAS_EM_THREAD", False):
        return False
    if "runserver" not in sys.argv:
        return False
    return os.environ.get("RUN_MAIN") == "true" or "--noreload" in sys.argv


def ligar():
    if not servindo_no_dev():
        return
    atexit.register(_ao_parar)
    request_started.connect(_na_primeira_requisicao, dispatch_uid="starhub-orfas")
