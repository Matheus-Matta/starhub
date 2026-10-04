"""Andamento da tarefa pelo WebSocket: o servidor empurra, a tela nao pergunta."""

import json
from unittest.mock import patch

import pytest
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser, Permission

from apps.core.models import User
from apps.core.tenant.context import tenant_context
from apps.integracoes import tempo_real
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from config.routing import websocket_urlpatterns

# O consumer le o banco em outra thread: so enxerga o que foi gravado de verdade.
pytestmark = pytest.mark.django_db(transaction=True)
APP = URLRouter(websocket_urlpatterns)


@pytest.fixture(autouse=True)
def _sem_loop_guardado():
    tempo_real._loop_do_servidor = None
    yield
    tempo_real._loop_do_servidor = None


def _tarefa(**campos):
    config = ConfiguracaoIntegracao.objects.get_or_create(nome="Shopify")[0]
    campos.setdefault("status", "running")
    return ExecucaoIntegracao.objects.create(
        configuracao=config, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR, **campos)


def _socket(usuario, tarefa):
    comunicador = WebsocketCommunicator(APP, f"/ws/tarefas/{tarefa.pk}/")
    comunicador.scope["user"] = usuario
    return comunicador


def _admin(conta):
    return User.objects.create_superuser("adm", "adm@x.test", "senha-forte-123", account=conta)


def test_ao_abrir_recebe_o_estado_e_depois_so_o_que_o_servidor_empurra(conta):
    """Antes a tela fazia um GET por segundo; agora uma conexao e mensagens so quando muda."""
    tarefa = _tarefa(progresso=20, etapa="Produtos: 2 de 10", processados=2, total=10)
    usuario = _admin(conta)

    async def cenario():
        socket = _socket(usuario, tarefa)
        conectou, _ = await socket.connect()
        assert conectou
        await socket.send_to(text_data=json.dumps({"type": "check_task_completion"}))
        inicial = json.loads(await socket.receive_from())
        await database_sync_to_async(ExecucaoIntegracao.objects.filter(pk=tarefa.pk).update)(
            progresso=70, processados=7, etapa="Produtos: 7 de 10")
        # Da thread da tarefa, como no dev: vai pelo loop que o consumer guardou.
        await database_sync_to_async(tempo_real.publicar)(tarefa.pk)
        empurrado = json.loads(await socket.receive_from())
        assert await socket.receive_nothing(timeout=0.3)  # nada alem do que mudou
        await socket.disconnect()
        return inicial, empurrado

    with tenant_context(conta):
        inicial, empurrado = async_to_sync(cenario)()
    assert inicial["progress"]["percent"] == 20.0 and inicial["complete"] is False
    assert empurrado["progress"]["description"] == "Produtos: 7 de 10"


def test_sem_login_ou_de_outra_conta_nao_conecta(conta, outra_conta):
    tarefa = _tarefa()
    operador = User.objects.create_user("op", "op@x.test", "senha-forte-123",
                                        account=outra_conta, is_staff=True)
    operador.user_permissions.add(Permission.objects.get(codename="view_execucaointegracao"))

    async def tenta(usuario):
        socket = _socket(usuario, tarefa)
        conectou, codigo = await socket.connect()
        return conectou, codigo

    assert async_to_sync(tenta)(AnonymousUser()) == (False, 4403)
    assert async_to_sync(tenta)(operador) == (False, 4403)


def test_no_worker_de_producao_envia_pelo_layer_sem_loop_guardado(conta):
    """Worker e outro processo: nao ha loop do servidor ali, o envio abre o proprio."""
    tarefa = _tarefa(progresso=50, etapa="Clientes: 5 de 10")
    layer = get_channel_layer()
    canal = async_to_sync(layer.new_channel)()
    async_to_sync(layer.group_add)(tempo_real.GRUPO.format(tarefa.pk), canal)
    tempo_real.publicar(tarefa.pk)
    mensagem = async_to_sync(layer.receive)(canal)
    assert mensagem["type"] == tempo_real.TIPO
    assert mensagem["dados"]["progress"]["percent"] == 50.0


def test_gravar_andamento_da_tarefa_publica(conta):
    from apps.integracoes.tasks import _gravar

    tarefa = _tarefa()
    with patch("apps.integracoes.tasks.publicar") as publicar:
        _gravar(tarefa, progresso=30)
    publicar.assert_called_once_with(tarefa.pk)
