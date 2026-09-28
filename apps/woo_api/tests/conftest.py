import base64

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from apps.core.models import User
from apps.woo_api.models import ChaveApi


@pytest.fixture
def usuario_erp(conta):
    usuario = User.objects.create_user(
        "erp", "erp@empresa.test", "senha-do-erp-123", account=conta
    )
    usuario.user_permissions.add(Permission.objects.get(codename="usar_api"))
    return usuario


def criar_chave(permissao=ChaveApi.Permissao.LEITURA_ESCRITA, **campos):
    """Chave da conta ativa (ou da `account` informada). Devolve (registro, ck_, cs_)."""
    registro = ChaveApi(descricao="ERP", permissao=permissao, **campos)
    chave, segredo = registro.gerar()
    registro.save()
    return registro, chave, segredo


def cliente_com_chave(chave, segredo):
    cliente = APIClient()
    credencial = base64.b64encode(f"{chave}:{segredo}".encode()).decode()
    cliente.credentials(HTTP_AUTHORIZATION=f"Basic {credencial}")
    return cliente


@pytest.fixture
def api(conta):
    """Cliente autenticado com chave ck_/cs_ de leitura e escrita (o caso comum)."""
    _, chave, segredo = criar_chave()
    return cliente_com_chave(chave, segredo)


@pytest.fixture
def par_somente_leitura(conta):
    _, chave, segredo = criar_chave(ChaveApi.Permissao.LEITURA)
    return chave, segredo


def json_com_numeros(cliente, metodo, url, corpo_texto):
    """Envia o JSON como TEXTO cru, para os numeros chegarem como numero
    (19.9 e nao "19.9") -- e assim que muitos ERPs mandam preco."""
    return getattr(cliente, metodo)(url, data=corpo_texto, content_type="application/json")
