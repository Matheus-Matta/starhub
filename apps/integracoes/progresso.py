"""Progresso das tarefas de integracao para a barra da tela (celery_progress).

Duas fontes, cada uma com seu papel:

- Celery (ProgressRecorder): o estado ao vivo da tarefa, que a barra le a cada segundo.
- Banco (ExecucaoIntegracao): a verdade. Sobrevive ao reinicio do worker e ao
  resultado que expira no backend; o fim da tarefa (Concluida, Falhou) vale por ele.

`estado()` devolve o JSON no formato que o celery_progress.js entende:

    {"complete": false, "success": null, "state": "PROGRESS",
     "progress": {"current": 12, "total": 40, "percent": 30.0, "description": "Buscando produtos"}}
"""

import logging

from celery import current_task
from celery.result import AsyncResult
from celery_progress.backend import Progress, ProgressRecorder

from apps.integracoes.models import ExecucaoIntegracao

ABERTAS = (ExecucaoIntegracao.Status.PENDENTE, ExecucaoIntegracao.Status.PROCESSANDO)
SUCESSO = (ExecucaoIntegracao.Status.CONCLUIDA, ExecucaoIntegracao.Status.CONCLUIDA_COM_FALHAS)

logger = logging.getLogger(__name__)


def registrar(processados, total, etapa):
    """Publica o passo no Celery; fora de uma tarefa (teste, shell) nao faz nada."""
    tarefa = current_task
    if not tarefa or not getattr(tarefa.request, "id", None):
        return
    try:
        ProgressRecorder(tarefa).set_progress(processados, total, description=etapa)
    except Exception:  # backend fora do ar nao pode derrubar a sincronizacao; o banco ja tem
        logger.warning("Progresso da tarefa %s nao foi publicado no Celery",
                       tarefa.request.id, exc_info=True)


def _do_banco(execucao):
    return {
        "pending": execucao.status == ExecucaoIntegracao.Status.PENDENTE,
        "current": execucao.processados, "total": execucao.total,
        "percent": float(execucao.progresso), "description": execucao.etapa,
    }


def _do_celery(execucao):
    if not execucao.celery_task_id:
        return None
    try:
        info = Progress(AsyncResult(execucao.celery_task_id)).get_info()
    except Exception:  # resultado ilegivel/backend fora: a barra segue pelo banco
        logger.warning("Progresso da tarefa %s ilegivel no Celery", execucao.pk, exc_info=True)
        return None
    return info.get("progress") if info.get("state") == "PROGRESS" else None


def estado(execucao):
    extras = {"status": execucao.status, "status_rotulo": execucao.get_status_display()}
    if execucao.status not in ABERTAS:
        # Terminou no banco: e o que vale, mesmo que o Celery ainda diga PROGRESS.
        sucesso = execucao.status in SUCESSO
        return {**extras, "complete": True, "success": sucesso,
                "state": "SUCCESS" if sucesso else "FAILURE",
                "progress": {**_do_banco(execucao), "percent": 100.0},
                "result": execucao.mensagem}
    progresso = _do_celery(execucao) or _do_banco(execucao)
    return {**extras, "complete": False, "success": None,
            "state": "PROGRESS", "progress": progresso}
