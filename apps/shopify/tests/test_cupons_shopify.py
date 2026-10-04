"""Cupom do pedido Shopify: consulta o desconto no Shopify e cadastra completo."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.core.models import ExternalReference, Origin
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Cupom, Pedido
from apps.loja.services.variantes import criar_produto
from apps.shopify import cupons
from apps.shopify.cliente import ShopifyErro
from apps.shopify.contexto import usando_configuracao
from apps.shopify.pedidos import importar_pedido
from apps.shopify.tests.pedido_exemplo import pedido_shopify, produto_shopify_falso  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("produto_shopify_falso")]

NODE = {
    "id": "gid://shopify/DiscountCodeNode/55",
    "codeDiscount": {
        "__typename": "DiscountCodeBasic", "title": "Promo de 10%",
        "summary": "10% off em Poltronas", "status": "ACTIVE",
        "startsAt": "2026-09-01T03:00:00Z", "endsAt": "2026-10-31T02:59:59Z",
        "usageLimit": 500, "appliesOncePerCustomer": True, "asyncUsageCount": 42,
        "codes": {"nodes": [{"code": "PROMO10"}]},
        "combinesWith": {"orderDiscounts": False, "productDiscounts": True,
                         "shippingDiscounts": False},
        "minimumRequirement": {"__typename": "DiscountMinimumSubtotal",
                               "greaterThanOrEqualToSubtotal": {"amount": "300.0",
                                                                "currencyCode": "BRL"}},
        "context": {"__typename": "DiscountBuyerSelectionAll", "all": "ALL"},
        "customerGets": {
            "value": {"__typename": "DiscountPercentage", "percentage": 0.1},
            "items": {"__typename": "DiscountProducts",
                      "products": {"nodes": [{"id": "gid://shopify/Product/9"}],
                                   "pageInfo": {"hasNextPage": False}},
                      "productVariants": {"nodes": [], "pageInfo": {"hasNextPage": False}}},
        },
    },
}


class ClienteFalso:
    chamadas = []
    resposta = {"codeDiscountNodeByCode": NODE}
    erro = None

    def __init__(self, configuracao):
        self.configuracao = configuracao

    def graphql(self, query, variables=None):
        ClienteFalso.chamadas.append(variables)
        if ClienteFalso.erro:
            raise ClienteFalso.erro
        return ClienteFalso.resposta


@pytest.fixture
def shopify(monkeypatch):
    ClienteFalso.chamadas, ClienteFalso.resposta = [], {"codeDiscountNodeByCode": NODE}
    ClienteFalso.erro = None
    monkeypatch.setattr(cupons, "ShopifyClient", ClienteFalso)
    configuracao = ConfiguracaoIntegracao.objects.create(
        nome="Shopify", dominio_loja="loja.myshopify.com")
    with usando_configuracao(configuracao):
        yield ClienteFalso


@pytest.fixture
def poltrona():
    produto = criar_produto("Poltrona", sku="POLTRONA-X", price=Decimal("100"))
    ExternalReference.objects.create(platform=Origin.SHOPIFY, entity_type="produtos",
                                     external_id="gid://shopify/Product/9",
                                     object_id=str(produto.pk))
    return produto


def test_codigo_desconhecido_consulta_o_shopify_e_cria_o_cupom_completo(shopify, poltrona):
    """Cupom criado so com codigo e valor perde datas, limites e produtos do Shopify."""
    pedido, _ = importar_pedido(pedido_shopify())

    assert shopify.chamadas == [{"code": "PROMO10"}]
    cupom = Cupom.objects.get()
    assert (cupom.name, cupom.description) == ("Promo de 10%", "10% off em Poltronas")
    assert (cupom.discount_type, cupom.value) == (Cupom.TipoDesconto.PERCENTUAL,
                                                  Decimal("10.00"))
    assert cupom.status == Cupom.Status.ATIVO
    assert cupom.starts_at == datetime(2026, 9, 1, 3, tzinfo=timezone.utc)
    assert cupom.ends_at == datetime(2026, 10, 31, 2, 59, 59, tzinfo=timezone.utc)
    assert (cupom.usage_limit, cupom.usage_limit_per_customer, cupom.usage_count) == (
        500, 1, 42)
    assert (cupom.minimum_requirement, cupom.minimum_subtotal) == (
        Cupom.RequisitoMinimo.SUBTOTAL, Decimal("300.00"))
    assert cupom.product_eligibility == Cupom.ElegibilidadeProduto.PRODUTOS
    assert list(cupom.produtos.all()) == [poltrona]
    assert cupom.stacking_policy == Cupom.Combinacao.COMBINA
    assert (cupom.free_shipping, cupom.origin) == (False, Origin.SHOPIFY)
    assert cupom.code != "PROMO10"
    assert ExternalReference.objects.filter(
        entity_type="cupons", external_id=NODE["id"], object_id=str(cupom.pk)).exists()
    assert pedido.linhas_cupom[0]["code"] == "PROMO10"


def test_segundo_pedido_com_o_mesmo_codigo_nao_chama_o_shopify(shopify, poltrona):
    """Uma consulta por pedido gastaria o limite da API e poderia criar outro cupom."""
    importar_pedido(pedido_shopify())
    importar_pedido(pedido_shopify(id=999, admin_graphql_api_id="gid://shopify/Order/999",
                                   name="#1002", order_number=1002))

    assert len(shopify.chamadas) == 1
    assert Cupom.objects.count() == 1
    assert Pedido.objects.count() == 2


def test_desconto_com_nome_ja_cadastrado_liga_no_existente(shopify):
    """O nome e a chave: o cupom do hub com o titulo do desconto nao pode duplicar."""
    existente = Cupom.objects.create(name="Promo de 10%", value=Decimal("5"),
                                     discount_type=Cupom.TipoDesconto.VALOR_FIXO)

    importar_pedido(pedido_shopify())

    assert Cupom.objects.get() == existente
    assert ExternalReference.objects.get(entity_type="cupons").object_id == str(existente.pk)


def test_codigo_que_o_shopify_nao_conhece_cria_pelo_codigo(shopify):
    """Desconto apagado no Shopify ainda precisa aparecer no hub pelo que o pedido diz."""
    shopify.resposta = {"codeDiscountNodeByCode": None}

    importar_pedido(pedido_shopify())

    cupom = Cupom.objects.get()
    assert (cupom.name, cupom.discount_type, cupom.value, cupom.status) == (
        "PROMO10", Cupom.TipoDesconto.PERCENTUAL, Decimal("10.00"), Cupom.Status.ATIVO)


def test_erro_da_api_do_shopify_desfaz_o_pedido(shopify):
    """Cupom criado pela metade some do reprocessamento; a execucao tem que falhar."""
    shopify.erro = ShopifyErro("API fora do ar")

    with pytest.raises(ShopifyErro):
        importar_pedido(pedido_shopify())

    assert not Pedido.objects.exists()
    assert not Cupom.objects.exists()
