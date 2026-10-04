"""WebSocket da tela da tarefa: /ws/tarefas/<id>/ (config/routing.py).

O navegador (celery_progress websockets.js) abre o socket e manda
{"type": "check_task_completion"}; a resposta e o estado atual. Depois disso so chega
mensagem quando a tarefa grava andamento (tempo_real.publicar): nada de perguntar a
cada segundo. O consumer do proprio celery_progress nao confere quem esta vendo;
este exige login, permissao de ver tarefas e a conta da tarefa.
"""

import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.integracoes import tempo_real

SEM_PERMISSAO = 4403  # fecha sem aceitar: a tela cai no "nao foi possivel atualizar"


class TarefaConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        tempo_real.lembrar_loop()
        self.execucao_id = int(self.scope["url_route"]["kwargs"]["pk"])
        if not await self._pode_ver():
            await self.close(code=SEM_PERMISSAO)
            return
        self.grupo = tempo_real.GRUPO.format(self.execucao_id)
        await self.channel_layer.group_add(self.grupo, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "grupo"):
            await self.channel_layer.group_discard(self.grupo, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # Unico pedido do cliente: o estado atual (ao abrir e ao reconectar).
        await self.send(text_data=json.dumps(await self._estado()))

    async def tarefa_progresso(self, evento):
        await self.send(text_data=json.dumps(evento["dados"]))

    @database_sync_to_async
    def _pode_ver(self):
        from apps.integracoes.models import ExecucaoIntegracao

        usuario = self.scope.get("user")
        if not (usuario and usuario.is_authenticated and usuario.is_active and usuario.is_staff):
            return False
        if not (usuario.has_perm("integracoes.view_execucaointegracao")
                or usuario.has_perm("integracoes.change_execucaointegracao")):
            return False
        conta = ExecucaoIntegracao.all_objects.filter(pk=self.execucao_id).values_list(
            "account_id", flat=True).first()
        # Mesma regra do admin: superusuario ve todas as contas; o resto, so a sua.
        return conta is not None and (usuario.is_superuser or conta == usuario.account_id)

    @database_sync_to_async
    def _estado(self):
        from apps.integracoes.models import ExecucaoIntegracao
        from apps.integracoes.progresso import estado

        execucao = ExecucaoIntegracao.all_objects.filter(pk=self.execucao_id).first()
        if execucao is None:
            return {"complete": True, "success": False, "result": "Tarefa nao encontrada."}
        return estado(execucao)
