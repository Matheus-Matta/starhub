"""enfileirar: no dev a tarefa longa roda numa thread, fora da requisicao."""

import threading
from unittest.mock import Mock

import pytest
from celery import shared_task

from apps.core.tarefas import enfileirar

comecou = threading.Event()
liberar = threading.Event()
terminou = threading.Event()
thread_da_tarefa = {}


@shared_task
def tarefa_lenta(valor, extra=None):
    thread_da_tarefa["nome"] = threading.current_thread().name
    comecou.set()
    liberar.wait(timeout=5)
    terminou.set()
    return (valor, extra)


@pytest.fixture
def eventos():
    for evento in (comecou, liberar, terminou):
        evento.clear()
    thread_da_tarefa.clear()
    yield
    liberar.set()  # teste que falhou no meio nao deixa a thread presa


def test_com_a_flag_ligada_a_chamada_volta_antes_da_tarefa_terminar(
    settings, eventos, transactional_db
):
    """Eager no dev rodava a sincronizacao inteira dentro do POST do admin e o Daphne
    matava a requisicao; o webhook da Shopify esperava a importacao inteira."""
    settings.STARHUB_TAREFAS_EM_THREAD = True

    resultado = enfileirar(tarefa_lenta, 1, extra="x")

    assert comecou.wait(timeout=5)
    assert not terminou.is_set()
    assert thread_da_tarefa["nome"] != threading.current_thread().name
    assert len(str(resultado.id)) == 36  # uuid para gravar em celery_task_id
    liberar.set()
    assert terminou.wait(timeout=5)


def test_dentro_de_transacao_a_thread_so_comeca_depois_do_commit(
    settings, eventos, db, django_capture_on_commit_callbacks
):
    """A thread usa outra conexao: comecando antes do commit, nao acharia a execucao
    que a requisicao acabou de criar."""
    settings.STARHUB_TAREFAS_EM_THREAD = True

    with django_capture_on_commit_callbacks(execute=True):
        enfileirar(tarefa_lenta, 1)
        assert not comecou.wait(timeout=0.3)

    assert comecou.wait(timeout=5)


def test_com_a_flag_desligada_chama_delay_como_no_prod(settings):
    """Prod (e os testes) precisam continuar indo para a fila do Celery."""
    settings.STARHUB_TAREFAS_EM_THREAD = False
    tarefa = Mock()
    tarefa.delay.return_value.id = "celery-1"

    resultado = enfileirar(tarefa, "a", b=2)

    tarefa.delay.assert_called_once_with("a", b=2)
    tarefa.apply.assert_not_called()
    assert resultado.id == "celery-1"


def test_testes_rodam_com_a_flag_desligada(settings):
    """O pytest usa config.settings.dev: sem desligar, os testes que conferem o
    resultado da tarefa leriam o banco antes da thread gravar."""
    assert settings.STARHUB_TAREFAS_EM_THREAD is False
