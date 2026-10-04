"""Barra de progresso das tarefas: Celery ao vivo (celery_progress), banco como verdade."""

import uuid

import pytest
from celery import current_app, shared_task
from celery.result import AsyncResult
from django.urls import reverse

from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.integracoes.progresso import estado, registrar

pytestmark = pytest.mark.django_db
VISTO = {}


@shared_task
def _tarefa_que_reporta():
    registrar(3, 12, "Buscando produtos")
    tarefa_id = _tarefa_que_reporta.request.id
    VISTO["durante"] = AsyncResult(tarefa_id).state, AsyncResult(tarefa_id).info


def _execucao(**campos):
    configuracao = ConfiguracaoIntegracao.objects.get_or_create(nome="Shopify")[0]
    return ExecucaoIntegracao.objects.create(
        configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR, **campos)


def _url(nome, execucao):
    return reverse(f"admin:integracoes_execucaointegracao_{nome}", args=[execucao.pk])


def test_registrar_publica_o_passo_no_celery_durante_a_tarefa():
    """Sem o PROGRESS no backend o celery_progress so veria a tarefa no fim."""
    _tarefa_que_reporta.apply(task_id=str(uuid.uuid4()))
    situacao, info = VISTO["durante"]
    assert situacao == "PROGRESS"
    assert (info["current"], info["total"], info["description"]) == (3, 12, "Buscando produtos")
    assert info["percent"] == 25.0


def test_registrar_fora_de_tarefa_nao_quebra():
    registrar(1, 2, "teste")  # shell, comando ou teste chamando o sincronizador direto


def test_aberta_sem_resultado_no_celery_anda_pelo_banco():
    """Worker reiniciado ou resultado expirado: a barra nao pode travar em zero."""
    execucao = _execucao(status="running", processados=5, total=10, progresso=50,
                         etapa="Buscando clientes", celery_task_id=str(uuid.uuid4()))
    dados = estado(execucao)
    assert dados["complete"] is False
    assert dados["progress"]["percent"] == 50.0
    assert dados["progress"]["description"] == "Buscando clientes"


def test_aberta_usa_o_progresso_ao_vivo_do_celery():
    tarefa_id = str(uuid.uuid4())
    current_app.backend.store_result(tarefa_id, {
        "pending": False, "current": 8, "total": 10, "percent": 80.0,
        "description": "Gravando"}, "PROGRESS")
    execucao = _execucao(status="running", progresso=50, celery_task_id=tarefa_id)
    assert estado(execucao)["progress"]["percent"] == 80.0


@pytest.mark.parametrize("status,sucesso", [
    ("completed", True), ("completed_errors", True), ("failed", False)])
def test_terminada_no_banco_encerra_a_barra(status, sucesso):
    """O banco manda no fim: Celery dizendo PROGRESS nao pode prender a tela."""
    tarefa_id = str(uuid.uuid4())
    current_app.backend.store_result(tarefa_id, {"current": 1, "total": 9}, "PROGRESS")
    execucao = _execucao(status=status, mensagem="Pronto", celery_task_id=tarefa_id)
    dados = estado(execucao)
    assert dados["complete"] is True and dados["success"] is sucesso
    assert dados["progress"]["percent"] == 100.0 and dados["result"] == "Pronto"


def test_tela_aberta_liga_a_barra_e_a_terminada_nao(admin_logado):
    execucao = _execucao(status="running", progresso=30)
    html = admin_logado.get(_url("change", execucao)).content.decode()
    assert f'data-tarefa-progresso="/ws/tarefas/{execucao.pk}/"' in html
    assert "celery_progress/websockets.js" in html
    assert 'value="30"' in html and "Marcar como falhou" in html
    ExecucaoIntegracao.objects.filter(pk=execucao.pk).update(status="completed", progresso=100)
    html = admin_logado.get(_url("change", execucao)).content.decode()
    assert "data-tarefa-progresso" not in html and "Marcar como falhou" not in html


def test_botao_marcar_como_falhou_libera_a_travada(admin_logado):
    execucao = _execucao(status="running")
    assert admin_logado.get(_url("liberar", execucao)).status_code == 405
    admin_logado.post(_url("liberar", execucao))
    assert ExecucaoIntegracao.objects.get(pk=execucao.pk).status == "failed"


def test_lista_mostra_barra_de_progresso(admin_logado):
    _execucao(status="running", progresso=45)
    html = admin_logado.get(reverse("admin:integracoes_execucaointegracao_changelist")).content
    assert b'<progress class="tarefa-barra tarefa-barra-info" value="45"' in html
