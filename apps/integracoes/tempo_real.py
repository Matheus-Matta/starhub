"""Progresso da tarefa empurrado pelo WebSocket (Channels), sem a tela perguntar.

Quem grava o andamento da tarefa (integracoes/execucao.gravar_aberta, integracoes/tasks._gravar)
chama `publicar(id)`: o estado (progresso.estado, formato do celery_progress) vai
para o grupo "tarefa-<id>", e o TarefaConsumer manda para quem esta com a tela aberta.

Dois caminhos de envio, porque o channel layer muda:
- dev: o InMemoryChannelLayer vive no processo do runserver e usa asyncio.Queue, que
  nao aceita envio de outra thread. A tarefa roda numa thread; a mensagem e entregue
  pelo loop do proprio servidor (run_coroutine_threadsafe), guardado no connect.
- prod: o worker e outro processo e o layer e o Redis; async_to_sync abre um loop so
  para o envio, e o pool do Redis e fechado no fim para nao vazar conexao por loop.
"""

import asyncio
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)
GRUPO = "tarefa-{}"
TIPO = "tarefa.progresso"  # -> TarefaConsumer.tarefa_progresso
_loop_do_servidor = None


def lembrar_loop():
    """Chamado no connect do consumer: o loop em que o servidor atende os sockets."""
    global _loop_do_servidor
    _loop_do_servidor = asyncio.get_running_loop()


async def _enviar_e_fechar(layer, grupo, mensagem):
    await layer.group_send(grupo, mensagem)
    if hasattr(layer, "close_pools"):
        await layer.close_pools()


def publicar(execucao_id):
    """Manda o estado atual da tarefa a quem a acompanha; falha aqui nunca derruba a tarefa."""
    from apps.integracoes.models import ExecucaoIntegracao
    from apps.integracoes.progresso import estado

    try:
        layer = get_channel_layer()
        execucao = ExecucaoIntegracao.all_objects.filter(pk=execucao_id).first()
        if layer is None or execucao is None:
            return
        grupo, mensagem = GRUPO.format(execucao.pk), {"type": TIPO, "dados": estado(execucao)}
        loop = _loop_do_servidor
        if loop is not None and loop.is_running() and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(layer.group_send(grupo, mensagem), loop)
        else:
            async_to_sync(_enviar_e_fechar)(layer, grupo, mensagem)
    except Exception:  # sem tela aberta ou layer fora: o banco ja tem o andamento
        logger.warning("Progresso da tarefa %s nao foi publicado no WebSocket", execucao_id,
                       exc_info=True)
