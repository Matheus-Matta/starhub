"""Fixtures dos testes de notificacao: fila do Celery, WebSocket e configuracao ligada."""

import pytest

from apps.core.models import User
from apps.notificacoes import entrega
from apps.notificacoes.contas import garantir


@pytest.fixture
def fila(monkeypatch):
    """Guarda (conta, aviso) em vez de mandar ao Celery."""
    avisos = []
    monkeypatch.setattr("apps.notificacoes.sinais.enfileirar",
                        lambda conta, aviso: avisos.append((conta, aviso)))
    return avisos


@pytest.fixture
def empurrados(monkeypatch):
    enviados = []
    monkeypatch.setattr(entrega, "enviar_ao_grupo", lambda g, m: enviados.append((g, m)))
    return enviados


def usuario_com(conta, nome, *permissoes, **campos):
    """Staff da conta com as permissoes dadas ("loja.view_pedido")."""
    from django.contrib.auth.models import Permission

    usuario = User.objects.create_user(nome, f"{nome}@x.test", "senha-forte-123",
                                       account=conta, is_staff=True, **campos)
    for permissao in permissoes:
        app, codigo = permissao.split(".")
        usuario.user_permissions.add(Permission.objects.get(content_type__app_label=app,
                                                            codename=codigo))
    return usuario


def ligar(conta, **regras):
    _email, configuracao = garantir(conta.pk)
    configuracao.ligado = True
    configuracao.regras = regras
    configuracao.save()
    return configuracao
