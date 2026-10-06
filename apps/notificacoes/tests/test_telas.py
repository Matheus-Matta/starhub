"""Telas de E-mail (SMTP) e Notificacoes, e o sino do cabecalho."""

import pytest
from django.urls import reverse

from apps.notificacoes.contas import garantir
from apps.notificacoes.models import ConfiguracaoEmail, ConfiguracaoNotificacao, Notificacao

pytestmark = pytest.mark.django_db
SMTP = "admin:notificacoes_configuracaoemail_changelist"
NOTIFICACOES = "admin:notificacoes_configuracaonotificacao_changelist"


def _abrir(cliente, nome):
    resposta = cliente.get(reverse(nome))
    assert resposta.status_code == 302, "o menu abre direto a configuracao da conta"
    return resposta.url


def test_smtp_salva_a_senha_criptografada_e_nao_a_mostra(admin_logado, conta):
    url = _abrir(admin_logado, SMTP)
    admin_logado.post(url, {"host": "smtp.loja.test", "porta": "587", "seguranca": "tls",
                            "usuario": "hub@loja.test", "senha": "senha-do-smtp",
                            "remetente_email": "hub@loja.test", "remetente_nome": "Loja"})

    smtp = ConfiguracaoEmail.objects.get()
    assert smtp.senha == "senha-do-smtp" and "senha-do-smtp" not in smtp.senha_criptografada
    assert "senha-do-smtp" not in admin_logado.get(url).content.decode()


def test_salvar_sem_senha_mantem_a_senha_e_teste_vai_para_a_fila(admin_logado, conta,
                                                                  monkeypatch):
    fila = []
    monkeypatch.setattr("apps.notificacoes.admin.enfileirar",
                        lambda tarefa, *args: fila.append((tarefa.name, args)))
    email, _ = garantir(conta.pk)
    email.senha = "antiga"
    email.save()
    url = _abrir(admin_logado, SMTP)

    admin_logado.post(url, {"host": "smtp.loja.test", "porta": "465", "seguranca": "ssl",
                            "usuario": "", "senha": "", "remetente_email": "hub@loja.test",
                            "remetente_nome": "", "testar": "on"})

    email.refresh_from_db()
    assert email.senha == "antiga" and email.porta == 465
    assert fila[0][0] == "apps.notificacoes.tasks.testar_email"
    assert fila[0][1][2] == "admin@starhub.test"


def test_notificacoes_comecam_desligadas_e_os_switches_viram_regras(admin_logado, conta):
    url = _abrir(admin_logado, NOTIFICACOES)
    tela = admin_logado.get(url).content.decode()
    assert "Pedido criado: navegador" in tela and "Avaliacao criada: e-mail" in tela

    admin_logado.post(url, {"ligado": "on", "destinatarios": "a@loja.test",
                            "pedido_criado__navegador": "on", "tarefa_falhou__email": "on"})

    configuracao = ConfiguracaoNotificacao.objects.get()
    assert configuracao.ligado is True
    assert configuracao.regras["pedido.criado"] == {"navegador": True, "email": False}
    assert configuracao.regras["tarefa.falhou"] == {"navegador": False, "email": True}
    assert configuracao.regras["produto.excluido"] == {"navegador": False, "email": False}


def test_sino_mostra_as_nao_lidas_e_marcar_como_lidas_zera(admin_logado, conta):
    usuario = admin_logado.session["_auth_user_id"]
    Notificacao.objects.create(usuario_id=usuario, evento="pedido.criado",
                               titulo="Pedido criado", mensagem="#SH-9")
    painel = admin_logado.get(reverse("admin:index"), HTTP_REFERER="").content.decode()
    assert 'data-notificacoes-contador' in painel and "#SH-9" in painel

    resposta = admin_logado.post(reverse("notificacoes_marcar_lidas"),
                                 HTTP_REFERER="http://testserver/admin/loja/pedido/")

    assert resposta.url == "http://testserver/admin/loja/pedido/"
    assert not Notificacao.objects.filter(lida=False).exists()


def test_marcar_lidas_nao_volta_para_site_de_fora(admin_logado):
    resposta = admin_logado.post(reverse("notificacoes_marcar_lidas"),
                                 HTTP_REFERER="https://golpe.test/")

    assert resposta.url == "/admin/"


def test_lista_de_recebidas_so_tem_as_do_proprio_usuario(admin_logado, conta):
    from apps.core.models import User

    outro = User.objects.create_user("outro", "o@x.test", "senha-forte-123", account=conta,
                                     is_staff=True)
    Notificacao.objects.create(usuario=outro, evento="x", titulo="Do outro")
    usuario = admin_logado.session["_auth_user_id"]
    Notificacao.objects.create(usuario_id=usuario, evento="x", titulo="Minha")

    lista = admin_logado.get(reverse("admin:notificacoes_notificacao_changelist")).content.decode()

    assert "Minha" in lista and "Do outro" not in lista


def test_email_alvo_e_obrigatorio_com_switch_de_email_e_validado(admin_logado, conta):
    url = _abrir(admin_logado, NOTIFICACOES)

    sem_alvo = admin_logado.post(url, {"ligado": "on", "pedido_criado__email": "on"})
    invalido = admin_logado.post(url, {"ligado": "on", "destinatarios": "a@loja.test, nao-e-email",
                                       "pedido_criado__email": "on"})
    admin_logado.post(url, {"ligado": "on", "destinatarios": " a@loja.test ; b@loja.test ",
                            "pedido_criado__email": "on"})

    assert "Cadastre ao menos um e-mail alvo" in sem_alvo.content.decode()
    assert "nao-e-email" in invalido.content.decode()
    alvo = ConfiguracaoNotificacao.objects.get().destinatarios
    assert alvo.splitlines() == ["a@loja.test", "b@loja.test"]
