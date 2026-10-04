"""Retomar tarefa que falhou: volta a mesma linha para a fila com o que ela precisa."""

from unittest.mock import Mock, patch

import pytest

from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.integracoes.retomar import NaoRetomavel, argumentos, retomar
from apps.integracoes.tasks import enviar_alteracao
from apps.loja.models import Produto

from .envio_falso import configuracao

pytestmark = pytest.mark.django_db
Tipo = ExecucaoIntegracao.Tipo


def _falha(tipo, config=None, **campos):
    config = config or ConfiguracaoIntegracao.objects.get_or_create(nome="Shopify")[0]
    campos.setdefault("status", "failed")
    return ExecucaoIntegracao.objects.create(configuracao=config, tipo=tipo, **campos)


def _retomar_capturando(execucao, capturar):
    fila = Mock(return_value=Mock(id="celery-novo"))
    with patch("apps.core.tarefas.enfileirar", fila), capturar(execute=True):
        retomar(execucao)
    return fila


def test_sincronizacao_volta_para_a_fila_na_mesma_linha(django_capture_on_commit_callbacks):
    execucao = _falha(Tipo.SINCRONIZAR, progresso=40, mensagem="caiu",
                      parametros={"direcao": "importar", "recursos": ["produtos"]})
    fila = _retomar_capturando(execucao, django_capture_on_commit_callbacks)
    tarefa, *args = fila.call_args.args
    assert tarefa.name.endswith("sincronizar_shopify") and args == [str(execucao.pk)]
    execucao.refresh_from_db()
    assert (execucao.status, execucao.progresso, execucao.mensagem) == ("pending", 0, "")
    assert execucao.celery_task_id == "celery-novo"
    assert ExecucaoIntegracao.objects.count() == 1


def test_envio_antigo_e_lido_da_mensagem():
    """Os envios de antes nao guardavam o pedido: a mensagem tem recurso, operacao e id."""
    execucao = _falha(Tipo.ENVIAR, mensagem="produtos update 15: timeout")
    caminho, args, kwargs = argumentos(execucao)
    assert caminho.endswith("enviar_alteracao")
    assert args == (str(execucao.configuracao_id), "produtos", "update", "15")
    assert kwargs == {"execucao_id": str(execucao.pk)}


def test_webhook_sem_corpo_guardado_nao_retoma_e_diz_o_caminho():
    with pytest.raises(NaoRetomavel, match="Sincronizar loja"):
        argumentos(_falha(Tipo.RECEBER))
    dados = {"id": 9, "title": "Mesa"}
    execucao = _falha(Tipo.RECEBER, parametros={"reenvio": {
        "recurso": "produtos", "operacao": "update", "dados": dados}})
    assert argumentos(execucao)[1] == (str(execucao.pk), "produtos", "update", dados)


def test_so_falha_volta_e_so_uma_vez(django_capture_on_commit_callbacks):
    """Dois cliques ao mesmo tempo: o UPDATE filtrado deixa entrar um so."""
    with pytest.raises(NaoRetomavel, match="so tarefa que falhou"):
        retomar(_falha(Tipo.WEBHOOKS, status="completed"))
    execucao = _falha(Tipo.WEBHOOKS)
    _retomar_capturando(execucao, django_capture_on_commit_callbacks)
    with pytest.raises(NaoRetomavel):
        retomar(execucao)


def test_sincronizacao_com_outra_rodando_e_recusada():
    config = ConfiguracaoIntegracao.objects.create(nome="Loja")
    _falha(Tipo.SINCRONIZAR, config, status="running")
    parada = _falha(Tipo.SINCRONIZAR, config, parametros={"direcao": "importar"})
    with pytest.raises(NaoRetomavel, match="outra sincronizacao"):
        retomar(parada)
    assert ExecucaoIntegracao.objects.get(pk=parada.pk).status == "failed"


def test_fila_fora_do_ar_devolve_para_falhou(django_capture_on_commit_callbacks):
    execucao = _falha(Tipo.WEBHOOKS)
    with patch("apps.core.tarefas.enfileirar", side_effect=ConnectionError("redis")), \
            django_capture_on_commit_callbacks(execute=True):
        retomar(execucao)
    execucao.refresh_from_db()
    assert execucao.status == "failed" and "redis" in execucao.mensagem


def test_envio_retomado_roda_de_novo_e_conclui(falsos, django_capture_on_commit_callbacks):
    """De ponta a ponta: o envio que falhou e retomado e chega ao marketplace."""
    config = configuracao("falso")
    produto = Produto.objects.create(nome="Mesa")
    enviar_alteracao.run(str(config.pk), "produtos", "create", str(produto.pk))
    execucao = ExecucaoIntegracao.objects.get(tipo=Tipo.ENVIAR)
    assert execucao.parametros["reenvio"] == {"recurso": "produtos", "operacao": "create",
                                              "pk": str(produto.pk)}
    ExecucaoIntegracao.objects.filter(pk=execucao.pk).update(status="failed")
    falsos.clear()
    with django_capture_on_commit_callbacks(execute=True):
        retomar(ExecucaoIntegracao.objects.get(pk=execucao.pk))
    assert ExecucaoIntegracao.objects.get(pk=execucao.pk).status == "completed"
    assert falsos  # o marketplace recebeu de novo
