# Rotas WebSocket. Cada app de marketplace que precisar de tempo real
# acrescenta as suas aqui.
from django.urls import path

from apps.integracoes.consumers import TarefaConsumer

websocket_urlpatterns = [
    # Andamento da tarefa de integracao (tela do admin), empurrado pelo servidor.
    path("ws/tarefas/<int:pk>/", TarefaConsumer.as_asgi()),
]
