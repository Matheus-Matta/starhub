from unittest.mock import Mock

import pytest
from celery.exceptions import Retry
from django.conf import settings

from apps.integracoes.envio import lote, lote_dev
from apps.integracoes.tasks import despachar_envios_pendentes


@pytest.fixture(autouse=True)
def fila_vazia():
    lote.limpar()
    yield
    lote.limpar()


def test_eventos_repetidos_de_requisicoes_diferentes_viram_um_so():
    """Cada PUT publicava no broker; uma rajada do ERP derrubava Redis e PostgreSQL."""
    lote.acumular("config-1", "produtos", "create", "566")
    lote.acumular("config-1", "produtos", "update", "566")
    lote.acumular("config-1", "produtos", "update", "566")

    token, eventos = lote.iniciar()

    assert [(item.configuracao_id, item.recurso, item.operacao, item.pk)
            for item in eventos] == [("config-1", "produtos", "create", "566")]
    lote.finalizar(token)


def test_confirmar_lote_nao_apaga_evento_mais_novo():
    """Um PUT durante o envio do lote nao pode ser apagado pela confirmacao do lote antigo."""
    lote.acumular("config-1", "produtos", "update", "566")
    token, eventos = lote.iniciar()
    antigo = eventos[0]

    lote.acumular("config-1", "produtos", "update", "566")
    lote.confirmar(token, antigo)
    lote.finalizar(token)
    proximo_token, proximos = lote.iniciar()

    assert len(proximos) == 1
    assert proximos[0].versao != antigo.versao
    lote.finalizar(proximo_token)


def test_delete_substitui_update_e_create_posterior_substitui_delete():
    """A compactacao precisa preservar o estado final, inclusive exclusao e recriacao."""
    lote.acumular("config-1", "produtos", "update", "566")
    lote.acumular("config-1", "produtos", "delete", "566")
    lote.acumular("config-1", "produtos", "create", "566")

    token, eventos = lote.iniciar()

    assert eventos[0].operacao == "create"
    lote.finalizar(token)


def test_worker_processa_varios_eventos_sem_publicar_uma_tarefa_por_item(monkeypatch):
    """O broker deve receber um pulso do beat, nao uma mensagem por produto salvo."""
    enviados = []
    monkeypatch.setattr(
        "apps.integracoes.tasks.enviar_alteracao.run",
        lambda *args: enviados.append(args) or {"status": "completed"},
    )
    lote.acumular("config-1", "produtos", "update", "566")
    lote.acumular("config-1", "produtos", "update", "577")

    resultado = despachar_envios_pendentes.run()

    assert resultado == {"processados": 2, "pendentes": 0}
    assert enviados == [
        ("config-1", "produtos", "update", "566"),
        ("config-1", "produtos", "update", "577"),
    ]


def test_beat_dispara_um_lote_a_cada_tres_segundos():
    """Uma janela curta compacta a rajada sem deixar produto parado por muito tempo."""
    agenda = settings.CELERY_BEAT_SCHEDULE["enviar-alteracoes-pendentes"]

    assert agenda["task"] == "apps.integracoes.tasks.despachar_envios_pendentes"
    assert agenda["schedule"].total_seconds() == 3


def test_dev_agenda_o_pulso_local_ao_receber_evento(monkeypatch):
    """Sem beat no runserver, o cache local nao pode ficar acumulado para sempre."""
    agendar = Mock()
    monkeypatch.setattr(lote_dev, "agendar", agendar)

    lote.acumular("config-1", "produtos", "update", "566")

    agendar.assert_called_once_with()


def test_falhas_do_lote_repetem_juntas_em_uma_unica_tarefa(monkeypatch):
    """A compactacao nao pode remover as tres tentativas que existiam no envio individual."""
    monkeypatch.setattr(
        "apps.integracoes.tasks.enviar_alteracao.run", lambda *_: {"status": "failed"}
    )
    monkeypatch.setattr("apps.integracoes.tasks.deve_repetir", lambda _request: True)
    repetir = Mock(side_effect=Retry())
    monkeypatch.setattr(despachar_envios_pendentes, "retry", repetir)
    lote.acumular("config-1", "produtos", "update", "566")

    with pytest.raises(Retry):
        despachar_envios_pendentes.run()

    assert repetir.call_count == 1
    assert repetir.call_args.kwargs["countdown"] == 30
