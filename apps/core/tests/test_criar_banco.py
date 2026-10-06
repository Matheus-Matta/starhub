"""Comando `criar_banco`: cria o POSTGRES_DB do .env so quando falta, e explica o erro."""

import psycopg
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.management.commands import criar_banco

POSTGRES = {"ENGINE": "django.db.backends.postgresql", "NAME": "starhub_loja",
            "USER": "starhub", "PASSWORD": "segredo", "HOST": "postgres", "PORT": "5432",
            "OPTIONS": {"sslmode": "prefer"}}


class ServidorFalso:
    """Conexao psycopg falsa: guarda o SQL e diz se o banco ja existe."""

    def __init__(self, bancos):
        self.bancos, self.sql, self.conectou = set(bancos), [], None

    def connect(self, **parametros):
        self.conectou = parametros
        return self

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        return False

    def execute(self, comando, parametros=None):
        texto = comando if isinstance(comando, str) else comando.as_string(None)
        self.sql.append(texto)
        self.achado = (1,) if parametros and parametros[0] in self.bancos else None
        return self

    def fetchone(self):
        return self.achado


@pytest.fixture
def servidor(monkeypatch):
    def montar(*bancos):
        falso = ServidorFalso(bancos)
        monkeypatch.setitem(criar_banco.connections["default"].settings_dict, "ENGINE",
                            POSTGRES["ENGINE"])
        for chave in ("NAME", "USER", "PASSWORD", "HOST", "PORT", "OPTIONS"):
            monkeypatch.setitem(criar_banco.connections["default"].settings_dict, chave,
                                POSTGRES[chave])
        monkeypatch.setattr(criar_banco.psycopg, "connect", falso.connect)
        return falso
    return montar


def test_cria_o_banco_do_env_quando_falta(servidor):
    falso = servidor("postgres")

    call_command("criar_banco", verbosity=0)

    assert falso.conectou["dbname"] == "postgres" and falso.conectou["autocommit"] is True
    assert falso.conectou["sslmode"] == "prefer"
    assert 'CREATE DATABASE "starhub_loja" OWNER "starhub"' in falso.sql
    assert falso.sql.count("SELECT pg_advisory_lock(%s)") == 1
    assert falso.sql.count("SELECT pg_advisory_unlock(%s)") == 1


def test_banco_que_ja_existe_nao_e_criado_de_novo(servidor):
    """Roda em toda subida do web: a segunda vez nao pode tentar criar."""
    falso = servidor("postgres", "starhub_loja")

    call_command("criar_banco", verbosity=0)

    assert not any(s.startswith("CREATE DATABASE") for s in falso.sql)


def test_sem_permissao_explica_o_que_fazer(servidor, monkeypatch):
    def recusa(**parametros):
        raise psycopg.OperationalError("permission denied to create database")

    servidor("postgres")
    monkeypatch.setattr(criar_banco.psycopg, "connect", recusa)

    with pytest.raises(CommandError, match="CREATEDB"):
        call_command("criar_banco", verbosity=0)


def test_sqlite_nao_faz_nada(capsys):
    call_command("criar_banco")

    assert "nada a criar" in capsys.readouterr().out
