"""Eventos dos models viram avisos: so com o switch ligado, um por commit."""

from decimal import Decimal

import pytest
from django.db import transaction

from apps.core.models import Account
from apps.integracoes import tempo_real
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.loja.models import Categoria, Pedido
from apps.notificacoes.contas import garantir
from apps.notificacoes.models import ConfiguracaoEmail, ConfiguracaoNotificacao
from apps.notificacoes.tests.conftest import ligar as _ligar

pytestmark = pytest.mark.django_db


def test_conta_nova_nasce_com_smtp_e_notificacoes_desligadas():
    conta = Account.objects.create(name="Loja Nova", slug="loja-nova")

    configuracao = ConfiguracaoNotificacao.all_objects.get(account=conta)
    assert ConfiguracaoEmail.all_objects.filter(account=conta).exists()
    assert configuracao.ligado is False and configuracao.regras == {}


def test_tudo_desligado_por_padrao_nada_e_agendado(conta, fila, django_capture_on_commit_callbacks):
    garantir(conta.pk)

    with django_capture_on_commit_callbacks(execute=True):
        Categoria.objects.create(nome="Sofas", slug="sofas")

    assert fila == []


def test_chave_geral_desligada_vence_o_switch_ligado(conta, fila,
                                                    django_capture_on_commit_callbacks):
    configuracao = _ligar(conta, **{"categoria.criado": {"navegador": True}})
    configuracao.ligado = False
    configuracao.save()

    with django_capture_on_commit_callbacks(execute=True):
        Categoria.objects.create(nome="Sofas", slug="sofas")

    assert fila == []


def test_criado_e_alterado_no_mesmo_commit_e_um_aviso_de_criado(
        conta, fila, django_capture_on_commit_callbacks):
    """Importar um pedido salva o Pedido varias vezes: sem isto, varios avisos."""
    _ligar(conta, **{"pedido.criado": {"navegador": True},
                     "pedido.alterado": {"navegador": True}})

    with django_capture_on_commit_callbacks(execute=True), transaction.atomic():
        pedido = Pedido.objects.create()
        pedido.total = Decimal("99.90")
        pedido.save()

    assert len(fila) == 1
    aviso = fila[0][1]
    assert aviso["evento"] == "pedido.criado" and "99.90" in aviso["mensagem"]
    assert aviso["link"].endswith(f"/loja/pedido/{pedido.pk}/change/")


def test_excluido_avisa_sem_link(conta, fila, django_capture_on_commit_callbacks):
    _ligar(conta, **{"categoria.excluido": {"navegador": True}})
    categoria = Categoria.objects.create(nome="Sofas", slug="sofas")

    with django_capture_on_commit_callbacks(execute=True):
        categoria.delete()

    aviso = fila[0][1]
    assert (aviso["titulo"], aviso["mensagem"], aviso["link"]) == (
        "Categoria excluida", "Sofas", "")


def test_tarefa_que_falhou_avisa(conta, fila, monkeypatch, django_capture_on_commit_callbacks):
    monkeypatch.setattr(tempo_real, "enviar_ao_grupo", lambda *a: None)
    _ligar(conta, **{"tarefa.falhou": {"navegador": True}})
    config = ConfiguracaoIntegracao.objects.create(nome="Shopify")
    tarefa = ExecucaoIntegracao.objects.create(configuracao=config, status="failed",
                                               tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR,
                                               mensagem="HTTP 401")

    with django_capture_on_commit_callbacks(execute=True):
        tempo_real.publicar(tarefa.pk)

    aviso = fila[0][1]
    assert aviso["evento"] == "tarefa.falhou" and "HTTP 401" in aviso["mensagem"]
