"""Comando `migrar`: no PostgreSQL migra dentro da trava e sempre a solta."""

import pytest
from django.core.management import call_command

from apps.core.management.commands import migrar

pytestmark = pytest.mark.django_db


class CursorFalso:
    def __init__(self, sql):
        self.sql = sql

    def __enter__(self):
        return self

    def __exit__(self, *erro):
        return False

    def execute(self, comando, parametros=None):
        self.sql.append(comando.split("(")[0])


def _postgres(monkeypatch, migrate):
    sql = []
    monkeypatch.setattr(migrar.connection, "vendor", "postgresql")
    monkeypatch.setattr(migrar.connection, "cursor", lambda: CursorFalso(sql))
    monkeypatch.setattr(migrar, "call_command", migrate)
    return sql


def test_postgres_migra_entre_pegar_e_soltar_a_trava(monkeypatch):
    """Blue e green subindo juntos aplicariam a mesma migration ao mesmo tempo."""
    ordem = []
    sql = _postgres(monkeypatch, lambda *a, **k: ordem.append(("migrate", list(sql))))

    call_command("migrar", verbosity=0)

    assert ordem == [("migrate", ["SELECT pg_advisory_lock"])]
    assert sql == ["SELECT pg_advisory_lock", "SELECT pg_advisory_unlock"]


def test_migrate_que_falha_ainda_solta_a_trava(monkeypatch):
    """Trava presa faria o proximo container esperar para sempre."""
    def quebra(*a, **k):
        raise RuntimeError("migration quebrou")

    sql = _postgres(monkeypatch, quebra)

    with pytest.raises(RuntimeError, match="migration quebrou"):
        call_command("migrar", verbosity=0)
    assert sql[-1] == "SELECT pg_advisory_unlock"


def test_sqlite_migra_direto_sem_trava(monkeypatch):
    chamadas = []
    monkeypatch.setattr(migrar, "call_command", lambda *a, **k: chamadas.append(a))

    call_command("migrar", verbosity=0)

    assert chamadas == [("migrate",)]
