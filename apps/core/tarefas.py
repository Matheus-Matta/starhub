"""Porta unica para disparar tarefa longa do Celery (sincronizacao, webhook, envio).

No prod e so `tarefa.delay()`: vai para o Redis e o worker roda. No dev o Celery
e eager (sem worker), e `.delay()` rodava a tarefa inteira DENTRO da requisicao:
o POST do admin ficava baixando o catalogo da Shopify ate o Daphne matar, e o
webhook da Shopify (que espera ~5s e reenvia) respondia depois da importacao.
Com `STARHUB_TAREFAS_EM_THREAD` (so no dev) a tarefa roda numa thread e a
requisicao volta na hora, como voltaria com um worker de verdade.
"""

import logging
import threading
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.db import connections, transaction

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TarefaEmThread:
    """Imita o AsyncResult no que o chamador usa: o `.id` gravado em celery_task_id."""

    id: str


def enfileirar(tarefa, *args, **kwargs):
    if not getattr(settings, "STARHUB_TAREFAS_EM_THREAD", False):
        return tarefa.delay(*args, **kwargs)
    task_id = str(uuid.uuid4())

    def rodar():
        try:
            # apply: mesma execucao do eager (request.is_eager, sem retry), so que aqui.
            tarefa.apply(args=args, kwargs=kwargs, task_id=task_id)
        except Exception:  # thread solta: sem isto o erro some sem rastro no terminal
            logger.exception("Tarefa %s (%s) falhou na thread do dev", tarefa.name, task_id)
        finally:
            # Conexao e por thread; a que a thread abriu nao seria fechada por ninguem.
            connections.close_all()

    def iniciar():
        threading.Thread(target=rodar, name=f"tarefa-{task_id[:8]}", daemon=True).start()

    # A thread usa outra conexao: so enxerga a execucao que a requisicao criou depois
    # do commit. Fora de transacao, on_commit roda na hora.
    transaction.on_commit(iniciar)
    return TarefaEmThread(task_id)
