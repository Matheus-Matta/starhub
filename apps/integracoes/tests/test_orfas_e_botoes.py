"""Tarefa orfa do dev vira Falhou; Retomar na lista e na tela; webhook guarda o corpo."""

from unittest.mock import Mock, patch

import pytest
from django.core.signals import request_started
from django.urls import reverse

from apps.integracoes import orfas
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao

pytestmark = pytest.mark.django_db
Tipo = ExecucaoIntegracao.Tipo


def _tarefa(status, tipo=Tipo.WEBHOOKS):
    config = ConfiguracaoIntegracao.objects.get_or_create(nome="Shopify")[0]
    return ExecucaoIntegracao.objects.create(configuracao=config, tipo=tipo, status=status)


def test_servidor_parado_marca_as_abertas_como_falhou():
    """A thread morre com o servidor: sem isto a tarefa ficava Processando para sempre."""
    rodando, na_fila, pronta = (_tarefa("running"), _tarefa("pending"), _tarefa("completed"))
    assert orfas.marcar_orfas(orfas.PAROU) == 2
    for tarefa in (rodando, na_fila):
        tarefa.refresh_from_db()
        assert tarefa.status == "failed" and "Retomar" in tarefa.mensagem
    pronta.refresh_from_db()
    assert pronta.status == "completed"


def test_primeira_requisicao_limpa_as_orfas_uma_vez_so():
    """Depois da primeira, as abertas sao deste processo e estao vivas."""
    request_started.connect(orfas._na_primeira_requisicao, dispatch_uid="starhub-orfas")
    try:
        _tarefa("running")
        request_started.send(sender=None)
        viva = _tarefa("running")
        request_started.send(sender=None)
    finally:
        request_started.disconnect(dispatch_uid="starhub-orfas")
    assert ExecucaoIntegracao.objects.get(pk=viva.pk).status == "running"
    assert ExecucaoIntegracao.objects.filter(status="failed").count() == 1


def test_fora_do_runserver_do_dev_nao_liga(settings, monkeypatch):
    """Teste, migrate, shell e prod nao podem derrubar tarefa de ninguem."""
    settings.STARHUB_TAREFAS_EM_THREAD = True  # o conftest raiz desliga
    monkeypatch.setattr("sys.argv", ["manage.py", "migrate"])
    assert orfas.servindo_no_dev() is False
    monkeypatch.setattr("sys.argv", ["manage.py", "runserver"])
    monkeypatch.setenv("RUN_MAIN", "true")
    assert orfas.servindo_no_dev() is True
    settings.STARHUB_TAREFAS_EM_THREAD = False
    assert orfas.servindo_no_dev() is False


def test_botao_retomar_so_na_falha_e_poe_na_fila(admin_logado, django_capture_on_commit_callbacks):
    tarefa = _tarefa("failed")
    url = reverse("admin:integracoes_execucaointegracao_change", args=[tarefa.pk])
    assert "Retomar" in admin_logado.get(url).content.decode()
    fila = Mock(return_value=Mock(id="c1"))
    with patch("apps.core.tarefas.enfileirar", fila), \
            django_capture_on_commit_callbacks(execute=True):
        admin_logado.post(reverse("admin:integracoes_execucaointegracao_retomar",
                                  args=[tarefa.pk]))
    assert fila.called and ExecucaoIntegracao.objects.get(pk=tarefa.pk).status == "pending"
    # Ja na fila: o botao some (retomar de novo poria a tarefa duas vezes na fila).
    assert "/retomar/" not in admin_logado.get(url).content.decode()


def test_acao_em_lote_retoma_as_falhas_e_explica_as_que_nao_da(
        admin_logado, django_capture_on_commit_callbacks):
    boa, sem_dados = _tarefa("failed"), _tarefa("failed", Tipo.RECEBER)
    lista = reverse("admin:integracoes_execucaointegracao_changelist")
    with patch("apps.core.tarefas.enfileirar", Mock(return_value=Mock(id="c1"))), \
            django_capture_on_commit_callbacks(execute=True):
        resposta = admin_logado.post(lista, {
            "action": "retomar_falhas", "_selected_action": [boa.pk, sem_dados.pk]},
            follow=True)
    textos = [str(m) for m in resposta.context["messages"]]
    assert any("1 tarefa(s) retomada(s)" in t for t in textos)
    assert any("Sincronizar loja" in t for t in textos)
    assert ExecucaoIntegracao.objects.get(pk=sem_dados.pk).status == "failed"
