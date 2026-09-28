"""A API ativa a conta de quem autenticou e nunca alcanca dado de outra conta.

Sem a conta padrao do conftest: assim o teste prova que a PROPRIA view ativa a
conta. Com um contexto externo ja aberto, um esquecimento na view passaria.
"""

import pytest
from rest_framework.test import APIClient

from apps.core.tenant.context import get_current_account_id, tenant_context
from apps.loja.models import Cliente, Produto
from apps.loja.services.variantes import criar_produto
from apps.woo_api.tests.conftest import cliente_com_chave, criar_chave

pytestmark = pytest.mark.sem_conta
URL = "/wp-json/wc/v1/products"


@pytest.fixture
def duas_lojas(conta, outra_conta):
    with tenant_context(conta):
        produto_a = criar_produto("Produto A", sku="SKU-1")
        _, chave, segredo = criar_chave()
    with tenant_context(outra_conta):
        # Mesmo SKU em outra conta e permitido: a unicidade e por conta.
        produto_b = criar_produto("Produto B", sku="SKU-1")
    return produto_a, produto_b, cliente_com_chave(chave, segredo)


def test_api_ativa_a_conta_da_chave_e_limpa_ao_terminar(duas_lojas):
    produto_a, _, api = duas_lojas
    assert [p["id"] for p in api.get(URL).json()] == [produto_a.pk]
    assert get_current_account_id(required=False) is None


@pytest.mark.parametrize("metodo", ["get", "put", "delete"])
def test_id_de_outra_conta_devolve_404_sem_alterar_nada(duas_lojas, metodo):
    """404 e nao 403: nao revela que o id existe em outra conta."""
    _, produto_b, api = duas_lojas
    url = f"{URL}/{produto_b.pk}?force=true"
    resposta = getattr(api, metodo)(url, {"name": "Invadido"}, format="json")
    assert resposta.status_code == 404
    with tenant_context(produto_b.account_id):
        assert Produto.objects.get(pk=produto_b.pk).nome == "Produto B"


def test_account_id_enviado_no_corpo_e_ignorado(duas_lojas, conta, outra_conta):
    _, _, api = duas_lojas
    corpo = {"name": "Novo", "account_id": str(outra_conta.pk), "account": str(outra_conta.pk)}
    assert api.post(URL, corpo, format="json").status_code == 201
    with tenant_context(outra_conta):
        assert not Produto.objects.filter(nome="Novo").exists()
    with tenant_context(conta):
        assert Produto.objects.filter(nome="Novo").exists()


def test_pedido_nao_referencia_cliente_nem_produto_de_outra_conta(duas_lojas, outra_conta):
    _, produto_b, api = duas_lojas
    with tenant_context(outra_conta):
        cliente_b = Cliente.objects.create(email="b@outra.test")
    pedidos = "/wp-json/wc/v1/orders"
    resposta = api.post(pedidos, {"customer_id": cliente_b.pk}, format="json")
    assert resposta.json()["code"] == "woocommerce_rest_invalid_customer_id"
    resposta = api.post(pedidos, {"line_items": [{"product_id": produto_b.pk}]}, format="json")
    assert resposta.json()["code"] == "woocommerce_rest_invalid_product_id"


def test_jwt_ativa_a_conta_do_usuario(duas_lojas, usuario_erp):
    produto_a, _, _ = duas_lojas
    cliente = APIClient()
    token = cliente.post("/wp-json/jwt-auth/v1/token", {
        "username": "erp", "password": "senha-do-erp-123",
    }, format="json").json()["token"]
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert [p["id"] for p in cliente.get(URL).json()] == [produto_a.pk]
