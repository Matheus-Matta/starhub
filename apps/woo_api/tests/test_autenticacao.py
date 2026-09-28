from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import User
from apps.woo_api.models import ChaveApi
from apps.woo_api.tests.conftest import cliente_com_chave, criar_chave

URL_TOKEN = "/wp-json/jwt-auth/v1/token"
URL_PRODUTOS = "/wp-json/wc/v1/products"


def test_token_jwt_devolve_o_mesmo_formato_do_plugin_do_wordpress(usuario_erp):
    resposta = APIClient().post(URL_TOKEN, {"username": "erp", "password": "senha-do-erp-123"},
                                format="json")
    assert resposta.status_code == 200
    assert set(resposta.json()) == {"token", "user_email", "user_nicename", "user_display_name"}
    assert resposta.json()["user_email"] == "erp@empresa.test"


def test_token_aceita_email_no_lugar_do_usuario(usuario_erp):
    resposta = APIClient().post(URL_TOKEN, {"username": "erp@empresa.test",
                                            "password": "senha-do-erp-123"}, format="json")
    assert resposta.status_code == 200


def test_senha_errada_devolve_403_com_codigo_do_plugin(usuario_erp):
    resposta = APIClient().post(URL_TOKEN, {"username": "erp", "password": "errada"},
                                format="json")
    assert resposta.status_code == 403
    assert resposta.json()["code"] == "[jwt_auth] incorrect_password"


def test_bearer_do_token_da_acesso_a_api(usuario_erp):
    cliente = APIClient()
    token = cliente.post(URL_TOKEN, {"username": "erp", "password": "senha-do-erp-123"},
                         format="json").json()["token"]
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert cliente.get(URL_PRODUTOS).status_code == 200
    validar = cliente.post("/wp-json/jwt-auth/v1/token/validate")
    assert validar.json()["code"] == "jwt_auth_valid_token"


def test_jwt_de_usuario_sem_permissao_da_api_e_recusado(conta):
    """Qualquer funcionario com login no admin conseguiria mexer no catalogo
    pela API se o token bastasse sozinho."""
    User.objects.create_user("vendedor", "v@empresa.test", "senha-vendedor-123", account=conta)
    cliente = APIClient()
    token = cliente.post(URL_TOKEN, {"username": "vendedor", "password": "senha-vendedor-123"},
                         format="json").json()["token"]
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert cliente.get(URL_PRODUTOS).status_code == 403


@pytest.mark.django_db
def test_token_invalido_devolve_codigo_do_plugin():
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION="Bearer nao-e-um-token")
    resposta = cliente.get(URL_PRODUTOS)
    assert resposta.status_code == 403
    assert resposta.json()["code"] == "jwt_auth_invalid_token"


@pytest.mark.django_db
def test_sem_credencial_devolve_401_no_formato_woo():
    resposta = APIClient().get(URL_PRODUTOS)
    assert resposta.status_code == 401
    assert resposta.json()["code"] == "woocommerce_rest_authentication_error"
    assert resposta.json()["data"]["status"] == 401


def test_chave_pela_query_string_funciona(par_somente_leitura):
    chave, segredo = par_somente_leitura
    resposta = APIClient().get(f"{URL_PRODUTOS}?consumer_key={chave}&consumer_secret={segredo}")
    assert resposta.status_code == 200


def test_segredo_errado_e_recusado(par_somente_leitura):
    chave, _ = par_somente_leitura
    resposta = APIClient().get(f"{URL_PRODUTOS}?consumer_key={chave}&consumer_secret=cs_errado")
    assert resposta.status_code == 401


def test_chave_somente_leitura_nao_grava(par_somente_leitura):
    chave, segredo = par_somente_leitura
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION="Basic " + __import__("base64").b64encode(
        f"{chave}:{segredo}".encode()).decode())
    resposta = cliente.post(URL_PRODUTOS, {"name": "X"}, format="json")
    assert resposta.status_code == 401
    assert resposta.json()["code"] == "woocommerce_rest_authentication_error"


def test_banco_guarda_so_o_hash_da_chave(par_somente_leitura):
    chave, segredo = par_somente_leitura
    registro = ChaveApi.objects.get()
    assert chave not in (registro.chave_hash, registro.segredo_hash)
    assert segredo not in (registro.chave_hash, registro.segredo_hash)


def test_login_jwt_aceita_json_enviado_como_text_plain(usuario_erp):
    """O ERP manda {"username","password"} (plugin JWT) as vezes sem o
    Content-Type application/json. Antes disso a resposta era 415."""
    resposta = APIClient().post(
        URL_TOKEN, data='{"username":"erp","password":"senha-do-erp-123"}',
        content_type="text/plain",
    )
    assert resposta.status_code == 200
    assert "token" in resposta.json()


@pytest.mark.parametrize("campos", [
    {"active": False},
    {"expires_at": timezone.now() - timedelta(minutes=1)},
])
def test_chave_inativa_ou_expirada_e_recusada(conta, campos):
    """Desativar a chave no admin precisa cortar o ERP na hora, sem apagar a chave."""
    _, chave, segredo = criar_chave(**campos)
    resposta = cliente_com_chave(chave, segredo).get(URL_PRODUTOS)
    assert resposta.status_code == 401


def test_chave_registra_ultimo_acesso(conta):
    registro, chave, segredo = criar_chave()
    cliente_com_chave(chave, segredo).get(URL_PRODUTOS)
    assert ChaveApi.objects.get(pk=registro.pk).last_used_at is not None
