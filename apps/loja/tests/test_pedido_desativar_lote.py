"""Acoes "Desativar pedidos" / "Reativar pedidos": a lista so enfileira, o worker aplica."""

import pytest
from django.urls import reverse

from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.retomar import argumentos
from apps.loja.models import Pedido
from apps.loja.tasks import ativar_pedidos

pytestmark = pytest.mark.django_db
LISTA = "/admin/loja/pedido/"


def _acao(admin_logado, acao, pedidos):
    return admin_logado.post(LISTA, {"action": acao, "_selected_action": [p.pk for p in pedidos]})


def _execucao():
    return ExecucaoIntegracao.objects.get(tipo=ExecucaoIntegracao.Tipo.ATIVAR_PEDIDOS)


def test_acao_enfileira_so_os_pedidos_que_mudam_e_o_worker_desativa(
        admin_logado, monkeypatch):
    """Milhares de pedidos selecionados nao podem rodar dentro da requisicao do admin."""
    fila = []
    monkeypatch.setattr("apps.loja.admin.pedidos_ativos.colocar_na_fila",
                        lambda *args: fila.append(args))
    um, dois = Pedido.objects.create(number="A1"), Pedido.objects.create(number="A2")
    ja_desativado = Pedido.objects.create(number="A3", active=False)

    resposta = _acao(admin_logado, "desativar_pedidos", [um, dois, ja_desativado])

    execucao = _execucao()
    assert execucao.parametros == {"pedidos": [um.pk, dois.pk], "ativo": False}
    assert resposta.url == reverse("admin:integracoes_execucaointegracao_change",
                                   args=[execucao.pk])
    assert Pedido.objects.filter(active=True).count() == 2, "nada muda antes do worker"

    resultado = ativar_pedidos.run(str(execucao.pk))

    assert set(Pedido.objects.filter(active=False).values_list("number", flat=True)) == {
        "A1", "A2", "A3"}
    assert resultado["message"].startswith("2 pedido(s): 2 desativado(s), 0 ja estava(m)")
    execucao.refresh_from_db()
    assert (execucao.status, execucao.progresso) == ("completed", 100)


def test_reativar_e_rodar_de_novo_e_seguro(admin_logado, monkeypatch):
    """Retomar roda a lista inteira de novo: quem ja mudou so e contado."""
    monkeypatch.setattr("apps.loja.admin.pedidos_ativos.colocar_na_fila", lambda *a: None)
    pedido = Pedido.objects.create(number="B1", active=False)

    _acao(admin_logado, "reativar_pedidos", [pedido])
    execucao = _execucao()
    ativar_pedidos.run(str(execucao.pk))
    pedido.refresh_from_db()
    assert pedido.active

    assert argumentos(execucao) == ("apps.loja.tasks.ativar_pedidos", (str(execucao.pk),), {})
    ExecucaoIntegracao.objects.filter(pk=execucao.pk).update(status="pending")
    resultado = ativar_pedidos.run(str(execucao.pk))
    assert "0 reativado(s), 1 ja estava(m) assim" in resultado["message"]


def test_desativacao_fica_no_historico_com_o_operador(admin_logado, monkeypatch):
    monkeypatch.setattr("apps.loja.admin.pedidos_ativos.colocar_na_fila", lambda *a: None)
    pedido = Pedido.objects.create(number="C1")

    _acao(admin_logado, "desativar_pedidos", [pedido])
    ativar_pedidos.run(str(_execucao().pk))

    # No worker nao ha request: o autor vem do updated_by, que a tarefa liga ao operador.
    ultimo = pedido.historical.order_by("-history_date").first()
    assert (ultimo.active, ultimo.updated_by.username) == (False, "admin")


def test_lista_marca_o_pedido_desativado(admin_logado):
    Pedido.objects.create(number="E1", active=False)
    assert "Desativado" in admin_logado.get(LISTA).content.decode()
