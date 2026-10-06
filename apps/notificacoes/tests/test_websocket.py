"""WebSocket do sino: cada usuario recebe so os proprios avisos, sem perguntar."""

import json

import pytest
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser, Permission

from apps.core.models import User
from apps.core.tenant.context import tenant_context
from apps.integracoes import tempo_real
from apps.notificacoes.contas import garantir
from apps.notificacoes.entrega import entregar
from config.routing import websocket_urlpatterns

pytestmark = pytest.mark.django_db(transaction=True)
APP = URLRouter(websocket_urlpatterns)


@pytest.fixture(autouse=True)
def _sem_loop_guardado():
    tempo_real._loop_do_servidor = None
    yield
    tempo_real._loop_do_servidor = None


def _socket(usuario):
    comunicador = WebsocketCommunicator(APP, "/ws/notificacoes/")
    comunicador.scope["user"] = usuario
    return comunicador


def test_aviso_novo_chega_so_para_os_usuarios_da_conta(conta, outra_conta):
    with tenant_context(conta):
        _email, configuracao = garantir(conta.pk)
        configuracao.ligado = True
        configuracao.regras = {"pedido.criado": {"navegador": True}}
        configuracao.save()
        ana = User.objects.create_user("ana", "a@x.test", "senha-forte-123", account=conta,
                                       is_staff=True)
        # Aviso de pedido so chega a quem pode ver pedidos (entrega.py).
        ana.user_permissions.add(Permission.objects.get(codename="view_pedido"))
    with tenant_context(outra_conta):
        bia = User.objects.create_user("bia", "b@x.test", "senha-forte-123",
                                       account=outra_conta, is_staff=True)
    aviso = {"evento": "pedido.criado", "titulo": "Pedido criado", "mensagem": "#SH-1",
             "link": ""}

    async def cenario():
        da_conta, de_fora = _socket(ana), _socket(bia)
        assert (await da_conta.connect())[0] and (await de_fora.connect())[0]

        def entregar_na_conta():
            with tenant_context(conta):
                entregar(str(conta.pk), aviso)

        await database_sync_to_async(entregar_na_conta)()
        recebido = json.loads(await da_conta.receive_from())
        assert await de_fora.receive_nothing(timeout=0.3)
        await da_conta.disconnect()
        await de_fora.disconnect()
        return recebido

    recebido = async_to_sync(cenario)()
    assert recebido["titulo"] == "Pedido criado" and recebido["lida"] is False


def test_sem_login_nao_conecta():
    async def cenario():
        conectou, codigo = await _socket(AnonymousUser()).connect()
        return conectou, codigo

    assert async_to_sync(cenario)() == (False, 4401)
