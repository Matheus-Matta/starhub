"""Worker morto (ou parado) nao pode travar a sincronizacao da loja para sempre."""

from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from apps.integracoes import sincronizacao
from apps.integracoes.exportar import Resumo
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.sincronizacao import (
    IMPORTAR,
    TEMPO_SEM_SINAL,
    SincronizacaoEmAndamento,
    iniciar,
    liberar_travada,
)
from apps.integracoes.tasks import exportar_dados
from apps.shopify.tasks import sincronizar_shopify

from .envio_falso import configuracao as config_falsa


@pytest.fixture
def config(falsos, monkeypatch):
    tarefa = Mock()
    tarefa.delay.return_value.id = "celery-1"
    monkeypatch.setattr(sincronizacao, "_tarefa", lambda _c, _d: tarefa)
    config = config_falsa("shopify", recursos=())
    matriz = config.permissoes
    matriz["receber"]["produtos"]["get"] = True
    config.permissoes = matriz
    config.save()
    return config


def _aberta(config, status, sem_sinal_ha):
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=config, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR, status=status,
    )
    ExecucaoIntegracao.objects.filter(pk=execucao.pk).update(
        updated_at=timezone.now() - sem_sinal_ha
    )
    return execucao


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["pending", "running"])
def test_aberta_sem_sinal_e_liberada_e_a_nova_e_criada(config, status):
    """Worker morto deixava a execucao aberta e o indice barrava toda sincronizacao nova."""
    velha = _aberta(config, status, TEMPO_SEM_SINAL + timedelta(minutes=1))

    nova = iniciar(config, IMPORTAR, ["produtos"])

    velha.refresh_from_db()
    assert nova.pk != velha.pk
    assert velha.status == ExecucaoIntegracao.Status.FALHOU
    assert velha.mensagem.startswith("Interrompida: sem sinal do worker desde ")
    assert velha.mensagem.endswith("; a sincronizacao nova foi liberada.")


@pytest.mark.django_db
def test_aberta_com_sinal_recente_continua_bloqueando(config):
    """Liberar uma que esta viva poe duas sincronizacoes da loja rodando juntas."""
    viva = _aberta(config, "running", TEMPO_SEM_SINAL - timedelta(minutes=5))

    with pytest.raises(SincronizacaoEmAndamento) as erro:
        iniciar(config, IMPORTAR, ["produtos"])

    viva.refresh_from_db()
    assert erro.value.execucao == viva
    assert viva.status == ExecucaoIntegracao.Status.PROCESSANDO


@pytest.mark.django_db
def test_liberar_travada_so_mexe_na_que_ainda_esta_aberta(config):
    """A acao do admin nao pode transformar uma concluida em falha."""
    aberta = _aberta(config, "running", timedelta(minutes=1))
    concluida = _aberta(config, "completed", timedelta(hours=2))

    assert liberar_travada(aberta) is True
    assert liberar_travada(concluida) is False

    aberta.refresh_from_db()
    concluida.refresh_from_db()
    assert aberta.status == ExecucaoIntegracao.Status.FALHOU
    assert concluida.status == ExecucaoIntegracao.Status.CONCLUIDA


def _progresso_renova_sinal(monkeypatch, alvo, tarefa, tipo, config):
    execucao = ExecucaoIntegracao.objects.create(configuracao=config, tipo=tipo)
    antigo = timezone.now() - timedelta(hours=1)
    vistos = []

    def trabalho(*args):
        progresso = args[-1] if tipo == "export" else args[1]
        ExecucaoIntegracao.objects.filter(pk=execucao.pk).update(updated_at=antigo)
        progresso(1, 2, "meio do caminho")
        vistos.append(ExecucaoIntegracao.objects.get(pk=execucao.pk).updated_at)
        return Resumo() if tipo == "export" else "ok"

    monkeypatch.setattr(alvo, trabalho)
    tarefa.run(str(execucao.pk))
    assert vistos and vistos[0] > antigo


@pytest.mark.django_db
def test_progresso_do_exportar_renova_o_sinal_de_vida(config, monkeypatch):
    """QuerySet.update() nao aplica auto_now: sem gravar updated_at, a viva parece morta."""
    _progresso_renova_sinal(
        monkeypatch, "apps.integracoes.exportar.exportar_dados", exportar_dados, "export", config
    )


@pytest.mark.django_db
def test_progresso_da_importacao_renova_o_sinal_de_vida(config, monkeypatch):
    """Importacao longa sem sinal seria liberada no meio e rodaria duas vezes."""
    _progresso_renova_sinal(
        monkeypatch, "apps.shopify.tasks.sincronizar_loja", sincronizar_shopify, "sync", config
    )


@pytest.mark.django_db
@pytest.mark.parametrize(("tarefa", "tipo"), [(exportar_dados, "export"),
                                               (sincronizar_shopify, "sync")])
def test_liberada_que_o_worker_pega_depois_nao_reabre(config, tarefa, tipo):
    """Worker que volta e roda a liberada batia no indice da nova (IntegrityError)."""
    liberada = ExecucaoIntegracao.objects.create(
        configuracao=config, tipo=tipo, status=ExecucaoIntegracao.Status.FALHOU,
        mensagem="Interrompida",
    )
    ExecucaoIntegracao.objects.create(configuracao=config, tipo=tipo)

    resultado = tarefa.run(str(liberada.pk))

    liberada.refresh_from_db()
    assert resultado["status"] == "ignored"
    assert liberada.status == ExecucaoIntegracao.Status.FALHOU
    assert liberada.mensagem == "Interrompida"


@pytest.mark.django_db
@pytest.mark.parametrize(("alvo", "tarefa", "tipo"), [
    ("apps.integracoes.exportar.exportar_dados", exportar_dados, "export"),
    ("apps.shopify.tasks.sincronizar_loja", sincronizar_shopify, "sync"),
])
def test_liberada_no_meio_nao_volta_a_andar_nem_vira_concluida(
    config, monkeypatch, alvo, tarefa, tipo
):
    """O worker lento terminava depois de liberado e trocava o FALHOU por CONCLUIDA."""
    execucao = ExecucaoIntegracao.objects.create(configuracao=config, tipo=tipo)

    def trabalho(*args):
        progresso = args[-1] if tipo == "export" else args[1]
        liberar_travada(ExecucaoIntegracao.objects.get(pk=execucao.pk))
        progresso(5, 10, "depois de liberada")
        return Resumo() if tipo == "export" else "terminei"

    monkeypatch.setattr(alvo, trabalho)
    tarefa.run(str(execucao.pk))

    execucao.refresh_from_db()
    assert execucao.status == ExecucaoIntegracao.Status.FALHOU
    assert execucao.mensagem.startswith("Interrompida: sem sinal")
    assert execucao.etapa == "Falhou"
