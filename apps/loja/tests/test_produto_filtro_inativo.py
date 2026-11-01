"""Filtro de status da lista de produtos com a opcao "Inativo"."""

import pytest

from apps.loja.models import Produto

pytestmark = pytest.mark.django_db
LISTA = "/admin/loja/produto/"


def test_status_inativo_mostra_so_os_produtos_fora_das_lojas(admin_logado):
    """O produto que o ERP cria nasce inativo: o operador precisa achar para ativar."""
    Produto.objects.create(nome="Ativo publicado", status="publish")
    Produto.objects.create(nome="Criado pelo ERP", status="draft", active=False)

    inativos = admin_logado.get(LISTA, {"status": "inativo"}).content.decode()
    publicados = admin_logado.get(LISTA, {"status": "publish"}).content.decode()

    assert "Criado pelo ERP" in inativos and "Ativo publicado" not in inativos
    assert "Ativo publicado" in publicados and "Criado pelo ERP" not in publicados
    assert "Inativo" in admin_logado.get(LISTA).content.decode()
