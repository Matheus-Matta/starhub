"""EnviadorNotificacao: navegador por permissao e e-mail so para o e-mail alvo."""

import pytest
from django.core import mail
from django.core.mail.backends.locmem import EmailBackend as Memoria

from apps.core.models import User
from apps.notificacoes.models import ConfiguracaoEmail, Notificacao
from apps.notificacoes.tasks import notificar
from apps.notificacoes.tests.conftest import ligar as _ligar
from apps.notificacoes.tests.conftest import usuario_com as _usuario

pytestmark = pytest.mark.django_db


def test_navegador_cria_uma_por_usuario_ativo_e_empurra_no_websocket(conta, empurrados):
    _ligar(conta, **{"pedido.criado": {"navegador": True}})
    ana = _usuario(conta, "ana", "loja.view_pedido")
    _usuario(conta, "inativo", "loja.view_pedido", is_active=False)
    aviso = {"evento": "pedido.criado", "titulo": "Pedido criado", "mensagem": "#SH-1",
             "link": "/admin/loja/pedido/1/change/"}

    resultado = notificar(str(conta.pk), aviso)

    assert resultado == {"navegador": 1, "email": 0}
    assert Notificacao.objects.get().usuario == ana
    assert empurrados[0][0] == f"notificacoes-{ana.pk}"
    assert empurrados[0][1]["dados"]["titulo"] == "Pedido criado"


def test_email_sai_pelo_smtp_da_conta_para_os_destinatarios(conta, monkeypatch, settings):
    settings.STARHUB_URL_PUBLICA = "https://hub.test"
    monkeypatch.setattr("apps.notificacoes.email.conexao", lambda cfg: Memoria())
    configuracao = _ligar(conta, **{"pedido.criado": {"email": True}})
    configuracao.destinatarios = "a@loja.test; b@loja.test"
    configuracao.save()
    ConfiguracaoEmail.objects.filter(account=conta).update(
        host="smtp.loja.test", remetente_email="hub@loja.test", remetente_nome="Loja")
    aviso = {"evento": "pedido.criado", "titulo": "Pedido criado", "mensagem": "#SH-1",
             "link": "/admin/loja/pedido/1/change/"}

    resultado = notificar(str(conta.pk), aviso)

    enviado = mail.outbox[0]
    assert resultado == {"navegador": 0, "email": 2}
    assert enviado.to == ["a@loja.test", "b@loja.test"]
    assert enviado.from_email == "Loja <hub@loja.test>"
    assert "https://hub.test/admin/loja/pedido/1/change/" in enviado.body
    assert not Notificacao.objects.exists()


def test_smtp_sem_servidor_nem_conecta_e_o_navegador_sai(conta, empurrados, monkeypatch):
    conexoes = []  # contar, nao lancar: o except da entrega engoliria o erro
    monkeypatch.setattr("apps.notificacoes.email.conexao",
                        lambda cfg: conexoes.append(cfg) or Memoria())
    configuracao = _ligar(conta, **{"pedido.criado": {"navegador": True, "email": True}})
    configuracao.destinatarios = "a@loja.test"
    configuracao.save()
    _usuario(conta, "ana", "loja.view_pedido")

    resultado = notificar(str(conta.pk), {"evento": "pedido.criado", "titulo": "t",
                                          "mensagem": "", "link": ""})

    assert resultado == {"navegador": 1, "email": 0} and conexoes == []


def test_navegador_so_para_quem_pode_ver_o_registro(conta, empurrados):
    """Quem nao ve pedidos nao recebe aviso de pedido; o superusuario ve tudo."""
    _ligar(conta, **{"pedido.criado": {"navegador": True},
                     "tarefa.falhou": {"navegador": True}})
    vendas = _usuario(conta, "vendas", "loja.view_pedido")
    estoque = _usuario(conta, "estoque", "loja.view_produto")
    chefe = User.objects.create_superuser("chefe", "c@x.test", "senha-forte-123", account=conta)

    notificar(str(conta.pk), {"evento": "pedido.criado", "titulo": "Pedido criado",
                              "mensagem": "", "link": ""})
    notificar(str(conta.pk), {"evento": "tarefa.falhou", "titulo": "Tarefa falhou",
                              "mensagem": "", "link": ""})

    recebidas = {(n.usuario_id, n.evento) for n in Notificacao.objects.all()}
    assert recebidas == {(vendas.pk, "pedido.criado"), (chefe.pk, "pedido.criado"),
                         (chefe.pk, "tarefa.falhou")}
    assert estoque.pk not in {u for u, _ in recebidas}


def test_email_so_vai_para_o_email_alvo(conta, monkeypatch):
    """Sem e-mail alvo, nenhum e-mail sai: nem para os usuarios da conta."""
    monkeypatch.setattr("apps.notificacoes.email.conexao", lambda cfg: Memoria())
    _ligar(conta, **{"pedido.criado": {"email": True}})
    ConfiguracaoEmail.objects.filter(account=conta).update(host="smtp.loja.test",
                                                           remetente_email="hub@loja.test")
    _usuario(conta, "ana", "loja.view_pedido")

    resultado = notificar(str(conta.pk), {"evento": "pedido.criado", "titulo": "t",
                                          "mensagem": "", "link": ""})

    assert resultado["email"] == 0 and mail.outbox == []
