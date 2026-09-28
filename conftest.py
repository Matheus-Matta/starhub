"""Fixtures comuns a todos os apps.

Todo teste que usa o banco roda dentro da conta `conta`, como rodaria uma
requisicao autenticada. Teste que precisa ver o sistema SEM conta ativa (o
proprio isolamento, a API ativando a conta sozinha) usa o marker `sem_conta`.
"""

import pytest

from apps.core.models import Account, User
from apps.core.tenant.context import tenant_context


def pytest_configure(config):
    config.addinivalue_line("markers", "sem_conta: nao ativa a conta padrao durante o teste")


@pytest.fixture
def conta(db):
    return Account.objects.create(name="Loja Teste", slug="loja-teste")


@pytest.fixture
def outra_conta(db):
    return Account.objects.create(name="Outra Loja", slug="outra-loja")


@pytest.fixture(autouse=True)
def _conta_ativa(request):
    usa_banco = "db" in request.fixturenames or request.node.get_closest_marker("django_db")
    if not usa_banco or request.node.get_closest_marker("sem_conta"):
        yield None
        return
    with tenant_context(request.getfixturevalue("conta")) as account_id:
        yield account_id


@pytest.fixture
def admin_logado(client, conta):
    usuario = User.objects.create_superuser(
        "admin", "admin@starhub.test", "senha-forte-123", account=conta
    )
    client.force_login(usuario)
    return client
