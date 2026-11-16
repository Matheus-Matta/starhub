"""Pulso local do lote; em producao o Celery beat faz este trabalho."""

import logging
import threading

from django.conf import settings
from django.db import connections

logger = logging.getLogger(__name__)
_guard = threading.Lock()
_timer = None


def agendar():
    global _timer
    if not getattr(settings, "STARHUB_TAREFAS_EM_THREAD", False):
        return
    with _guard:
        if _timer is not None and _timer.is_alive():
            return
        _timer = threading.Timer(3, _rodar)
        _timer.name = "envios-em-lote"
        _timer.daemon = True
        _timer.start()


def _rodar():
    global _timer
    try:
        from apps.integracoes.tasks import despachar_envios_pendentes

        despachar_envios_pendentes.run()
    except Exception:
        logger.exception("Nao foi possivel processar os envios acumulados do dev")
    finally:
        connections.close_all()
        with _guard:
            _timer = None
        from apps.integracoes.envio import lote

        if lote.ha_pendentes():
            agendar()
