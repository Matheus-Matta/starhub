"""Conferencia dos pedidos pelo beat (a cada 30 min e quando o beat sobe).

Webhook perdido (loja fora, hub fora, rede) deixava o pedido fora do hub ate alguem
sincronizar a mao. A conferencia busca na loja os pedidos criados ou alterados na
janela e passa pelo mesmo importador da sincronizacao (casa pelo id externo e SKU).
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.conf import settings

from apps.core.models import ExternalReference
from apps.core.tenant.context import tenant_context
from apps.integracoes import conferencia
from apps.integracoes.models import ExecucaoIntegracao
from apps.suri.tests import loja_falsa as suri
from apps.woocommerce.tests import loja_falsa as woo

pytestmark = pytest.mark.django_db
AGORA = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
CINCO = timedelta(minutes=5)
PEDIDOS = (("pedidos", "get"), ("pedidos", "create"), ("pedidos", "update"))


def _pedido_recebido(conta, plataforma, quando, externo="1"):
    with tenant_context(conta.pk):
        ref = ExternalReference.objects.create(platform=plataforma, entity_type="pedidos",
                                               object_id="1", external_id=externo)
    ExternalReference.all_objects.filter(pk=ref.pk).update(created_at=quando)


def _conferencia(cfg, conferido_ate, status=ExecucaoIntegracao.Status.CONCLUIDA):
    return ExecucaoIntegracao.all_objects.create(
        account_id=cfg.account_id, configuracao=cfg, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR,
        status=status, parametros={"direcao": "importar", "recursos": ["pedidos"],
                                   "janela": {"conferido_ate": conferido_ate.isoformat()}})


def _limites(cfg):
    return conferencia.limites(conferencia.janela(cfg, AGORA))


def test_primeira_conferencia_comeca_no_ultimo_pedido_recebido_menos_5_min(conta):
    cfg = woo.configuracao(conta, receber=PEDIDOS)
    ultimo = AGORA - timedelta(hours=3)
    _pedido_recebido(conta, "woocommerce", ultimo - timedelta(days=2), externo="velho")
    _pedido_recebido(conta, "woocommerce", ultimo)
    _pedido_recebido(conta, "shopify", AGORA - timedelta(minutes=1), externo="outra-loja")

    assert _limites(cfg) == (ultimo - CINCO, AGORA + CINCO)


def test_conferencia_seguinte_comeca_onde_a_anterior_parou(conta):
    """Pelo ultimo pedido, o pedido perdido antes de um que chegou bem nunca entrava.

    Webhook do pedido A (10:00) perdido, pedido B chegou as 10:20: a janela pelo ultimo
    pedido comecaria 10:15 e o A ficava de fora para sempre.
    """
    cfg = woo.configuracao(conta, receber=PEDIDOS)
    anterior = AGORA - timedelta(minutes=30)
    _conferencia(cfg, anterior)
    _pedido_recebido(conta, "woocommerce", AGORA - timedelta(minutes=10))

    assert _limites(cfg) == (anterior - CINCO, AGORA + CINCO)


def test_conferencia_que_falhou_nao_avanca_a_janela(conta):
    cfg = woo.configuracao(conta, receber=PEDIDOS)
    boa = AGORA - timedelta(hours=2)
    _conferencia(cfg, boa)
    _conferencia(cfg, AGORA - timedelta(minutes=30), status=ExecucaoIntegracao.Status.FALHOU)

    assert _limites(cfg)[0] == boa - CINCO


def test_loja_sem_pedido_nem_conferencia_olha_o_ultimo_dia(conta):
    cfg = woo.configuracao(conta, receber=PEDIDOS)

    assert _limites(cfg) == (AGORA - timedelta(days=1) - CINCO, AGORA + CINCO)


def test_beat_confere_so_loja_ativa_com_buscar_pedidos(conta, outra_conta):
    ativa = woo.configuracao(conta, receber=PEDIDOS)
    sem_buscar = suri.configuracao(conta, receber=(("pedidos", "create"),))
    with tenant_context(outra_conta.pk):
        desligada = suri.configuracao(outra_conta, receber=PEDIDOS)
        desligada.active = False
        desligada.save()

    execucoes = conferencia.conferir_lojas(AGORA)

    assert [e.configuracao_id for e in execucoes] == [ativa.pk]
    criada = ExecucaoIntegracao.all_objects.get()
    assert criada.parametros["recursos"] == ["pedidos"]
    assert criada.parametros["janela"]["conferido_ate"] == AGORA.isoformat()
    assert sem_buscar.pk != criada.configuracao_id


def test_sincronizacao_ja_rodando_pula_a_loja_sem_erro(conta):
    """Duas buscas da mesma loja ao mesmo tempo sao barradas pelo indice do banco."""
    cfg = woo.configuracao(conta, receber=PEDIDOS)
    ExecucaoIntegracao.all_objects.create(
        account_id=conta.pk, configuracao=cfg, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR,
        status=ExecucaoIntegracao.Status.PROCESSANDO)

    assert conferencia.conferir_lojas(AGORA) == []
    assert ExecucaoIntegracao.all_objects.count() == 1


def test_beat_agenda_a_conferencia_a_cada_30_minutos():
    agenda = settings.CELERY_BEAT_SCHEDULE["conferir-pedidos-das-lojas"]

    assert agenda["task"] == "apps.integracoes.conferencia.conferir_pedidos_das_lojas"
    assert agenda["schedule"] == timedelta(minutes=30)


def test_subida_do_beat_confere_na_hora(monkeypatch):
    """Sistema que ficou fora nao espera 30 min: a janela ja cobre o tempo parado."""
    from config import celery

    enviadas = []
    monkeypatch.setattr(celery.app, "send_task", lambda nome, **_: enviadas.append(nome))

    celery.conferir_ao_subir()

    assert enviadas == ["apps.integracoes.conferencia.conferir_pedidos_das_lojas"]
