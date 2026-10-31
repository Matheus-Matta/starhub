"""Pedido do Shopify chega ao ERP com o CPF do checkout, no pedido e no cadastro."""

from decimal import Decimal

import pytest

from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Cliente, Pedido
from apps.loja.services.variantes import criar_produto
from apps.shopify.cliente import ShopifyClient
from apps.shopify.contexto import coletando_avisos, usando_configuracao
from apps.shopify.pedidos_documento import CONSULTA_DOCUMENTO
from apps.shopify.tests.pedido_exemplo import pedido_shopify, produto_shopify_falso  # noqa: F401
from apps.shopify.webhooks import processar_webhook

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("produto_shopify_falso")]
CPF = "39053344705"


@pytest.fixture
def loja(monkeypatch):
    """Shopify falso: so a consulta do documento do checkout traz dados."""
    def graphql(self, query, variables=None):
        if query != CONSULTA_DOCUMENTO:
            return {}
        return {"order": {"localizationExtensions": {"nodes": [
            {"purpose": "TAX", "countryCode": "BR", "title": "CPF/CNPJ", "value": CPF}]}}}

    monkeypatch.setattr(ShopifyClient, "graphql", graphql)
    criar_produto("Poltrona Exemplo", sku="POLTRONA-001", price=Decimal("1499.90"))
    return ConfiguracaoIntegracao.objects.create(nome="Shopify",
                                                 dominio_loja="loja.myshopify.com")


def _receber(loja, dados):
    with usando_configuracao(loja):
        processar_webhook(loja, "pedidos", "create", dados, lambda *_: None)


def test_order_do_shopify_sai_com_o_cpf_do_checkout_e_o_cliente_fica_com_ele(api, loja):
    """O webhook nao traz o CPF: sem a consulta o ERP recebia billing.cpf vazio e nao
    conseguia cadastrar o cliente."""
    _receber(loja, pedido_shopify(note_attributes=[]))
    pedido = Pedido.objects.get()

    billing = api.get(f"/wp-json/wc/v3/orders/{pedido.pk}").json()["billing"]
    assert (billing["cpf"], billing["persontype"]) == (CPF, "F")
    assert (pedido.cliente.cpf, pedido.cliente.tipo_documento) == (CPF, "cpf")
    cliente = api.get(f"/wp-json/wc/v1/customers/{pedido.cliente_id}").json()
    assert cliente["billing"]["cpf"] == CPF


def test_cpf_ja_no_cadastro_do_cliente_nao_e_trocado(loja):
    """O operador pode ter corrigido o CPF no hub; o pedido seguinte nao desfaz."""
    Cliente.objects.create(email="maria@example.com", cpf="52998224725")
    _receber(loja, pedido_shopify(note_attributes=[]))
    assert Pedido.objects.get().cliente.cpf == "52998224725"


def test_cpf_de_outro_cliente_avisa_e_o_pedido_entra(loja):
    """O indice unico de CPF barraria o cadastro; o pedido nao pode cair junto."""
    Cliente.objects.create(email="outro@example.com", cpf=CPF)
    with coletando_avisos() as avisos:
        _receber(loja, pedido_shopify(note_attributes=[]))
    pedido = Pedido.objects.get()
    assert pedido.cliente.cpf == ""
    assert pedido.endereco_cobranca.metadata["cpf"] == CPF
    assert "ja e de outro cliente" in str(avisos)
