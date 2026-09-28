"""O schema nasce so das migrations (reset DEV do Sprint Log).

O pytest-django monta o banco de teste do zero rodando TODAS as migrations; se
alguma quebrar num banco vazio, a sessao inteira falha antes deste teste.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db


def test_banco_limpo_fica_sem_migration_pendente():
    executor = MigrationExecutor(connection)
    assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []


def test_models_nao_tem_mudanca_sem_migration():
    """makemigrations --check sai com SystemExit(1) se um model mudou sem migration."""
    call_command("makemigrations", "--check", "--dry-run", stdout=StringIO())
