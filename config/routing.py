# Rotas WebSocket. Cada app de marketplace que precisar de tempo real
# acrescenta as suas aqui.
from django.urls import path

from apps.integracoes.consumers import TarefaConsumer
from apps.notificacoes.consumers import NotificacaoConsumer

websocket_urlpatterns = [
    # Andamento da tarefa de integracao (tela do admin), empurrado pelo servidor.
    path("ws/tarefas/<int:pk>/", TarefaConsumer.as_asgi()),
    # Sino do cabecalho: aviso novo chega na hora (apps/notificacoes/entrega.py).
    path("ws/notificacoes/", NotificacaoConsumer.as_asgi()),
]
