"""Primeiros passos num banco novo: criar a conta e depois o superusuario dela."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.core.models import Account, User

pytestmark = [pytest.mark.django_db, pytest.mark.sem_conta]


def test_criar_conta_e_createsuperuser_com_a_conta():
    """createsuperuser entrega o id digitado (texto), nao a instancia de Account."""
    saida = StringIO()
    call_command("criar_conta", "Minha Loja", stdout=saida)
    conta = Account.objects.get(slug="minha-loja")
    assert str(conta.pk) in saida.getvalue()
    call_command("createsuperuser", "--noinput", "--username", "root", "--email", "r@x.test",
                 "--account", str(conta.pk), stdout=StringIO())
    assert User.objects.get(username="root").account == conta


def test_criar_conta_recusa_slug_repetido():
    call_command("criar_conta", "Minha Loja", stdout=StringIO())
    with pytest.raises(CommandError):
        call_command("criar_conta", "Minha Loja", stdout=StringIO())


def _env(tmp_path, texto):
    arquivo = tmp_path / ".env"
    arquivo.write_text(texto, encoding="utf-8")
    return str(arquivo)


ENV_DEV = "# comentario\nUSER_ADMIN=admin\nPASSWORD_ADMIN='admin'\nACCOUNT_ADMIN=starhub\n"


def test_conta_inicial_cria_conta_e_superusuario_do_env(tmp_path, settings, monkeypatch):
    settings.DEBUG = True
    for nome in ("USER_ADMIN", "PASSWORD_ADMIN", "ACCOUNT_ADMIN", "EMAIL_ADMIN"):
        monkeypatch.delenv(nome, raising=False)
    call_command("criar_conta_inicial", "--env", _env(tmp_path, ENV_DEV), stdout=StringIO())
    usuario = User.objects.get(username="admin")
    assert usuario.is_superuser and usuario.check_password("admin")
    assert usuario.account.slug == "starhub"


def test_conta_inicial_pode_rodar_de_novo_sem_trocar_a_senha(tmp_path, settings, monkeypatch):
    """Rodar no deploy toda vez nao pode resetar a senha que o admin ja trocou."""
    settings.DEBUG = True
    for nome in ("USER_ADMIN", "PASSWORD_ADMIN", "ACCOUNT_ADMIN"):
        monkeypatch.delenv(nome, raising=False)
    env = _env(tmp_path, ENV_DEV)
    call_command("criar_conta_inicial", "--env", env, stdout=StringIO())
    usuario = User.objects.get(username="admin")
    usuario.set_password("senha-nova-forte-123")
    usuario.save()
    call_command("criar_conta_inicial", "--env", env, stdout=StringIO())
    assert Account.objects.count() == 1
    assert User.objects.get(username="admin").check_password("senha-nova-forte-123")


def test_conta_inicial_recusa_senha_fraca_em_producao(tmp_path, settings, monkeypatch):
    settings.DEBUG = False
    for nome in ("USER_ADMIN", "PASSWORD_ADMIN", "ACCOUNT_ADMIN"):
        monkeypatch.delenv(nome, raising=False)
    with pytest.raises(CommandError, match="Senha fraca"):
        call_command("criar_conta_inicial", "--env", _env(tmp_path, ENV_DEV), stdout=StringIO())
    assert not User.objects.exists() and not Account.objects.exists()


def test_conta_inicial_avisa_o_que_falta_no_env(tmp_path, monkeypatch):
    for nome in ("USER_ADMIN", "PASSWORD_ADMIN", "ACCOUNT_ADMIN"):
        monkeypatch.delenv(nome, raising=False)
    with pytest.raises(CommandError, match="PASSWORD_ADMIN"):
        call_command("criar_conta_inicial", "--env", _env(tmp_path, "USER_ADMIN=admin\n"),
                     stdout=StringIO())
