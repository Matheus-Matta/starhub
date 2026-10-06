"""WebSocket do sino do cabecalho: /ws/notificacoes/ (config/routing.py).

Cada usuario logado entra no grupo dele ("notificacoes-<id>"); a entrega
(entrega.py) empurra o aviso novo e o navegador poe no dropdown e soma no contador.
Nada e perguntado em intervalo: o servidor avisa quando tem.
"""

import json

from channels.generic.websocket import AsyncWebsocketConsumer

from apps.integracoes import tempo_real
from apps.notificacoes.entrega import GRUPO

SEM_LOGIN = 4401


class NotificacaoConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        tempo_real.lembrar_loop()
        usuario = self.scope.get("user")
        if not (usuario and usuario.is_authenticated and usuario.is_active and usuario.is_staff):
            await self.close(code=SEM_LOGIN)
            return
        self.grupo = GRUPO.format(usuario.pk)
        await self.channel_layer.group_add(self.grupo, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "grupo"):
            await self.channel_layer.group_discard(self.grupo, self.channel_name)

    async def notificacao_nova(self, evento):
        await self.send(text_data=json.dumps(evento["dados"]))
