import pytest

from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.shopify import sincronizar
from apps.shopify.pedidos_graphql import pedido_graphql_para_rest


def _dinheiro(valor):
    return {"shopMoney": {"amount": valor, "currencyCode": "BRL"}}


def _alocacao(valor, indice):
    return {"allocatedAmountSet": _dinheiro(valor), "discountApplication": {"index": indice}}


ENDERECO = {
    "firstName": "Maria", "lastName": "Silva", "address1": "Rua das Flores, 100",
    "address2": "Apto 10, Centro", "city": "São Paulo", "province": "São Paulo",
    "provinceCode": "SP", "zip": "01000-000", "country": "Brazil", "countryCodeV2": "BR",
    "phone": "+5511999999999", "company": None,
}

NODE = {
    "id": "gid://shopify/Order/123456789", "legacyResourceId": "123456789",
    "name": "#1001", "email": "maria@example.com", "phone": None,
    "createdAt": "2026-09-01T12:00:00Z", "updatedAt": "2026-09-01T12:05:00Z",
    "processedAt": "2026-09-01T12:00:00Z", "cancelledAt": None, "cancelReason": None,
    "note": "Observação do pedido",
    "customAttributes": [{"key": "Agendamento", "value": "2026-10-15"},
                         {"key": "tipo_entrega", "value": "delivery"}],
    "displayFinancialStatus": "PAID", "displayFulfillmentStatus": "UNFULFILLED",
    "paymentGatewayNames": ["appmax_pix"], "currencyCode": "BRL",
    "totalPriceSet": _dinheiro("1889.79"), "subtotalPriceSet": _dinheiro("1849.89"),
    "totalDiscountsSet": _dinheiro("150"), "totalShippingPriceSet": _dinheiro("39.9"),
    "customer": {"id": "gid://shopify/Customer/55", "legacyResourceId": "55",
                 "email": "maria@example.com", "firstName": "Maria", "lastName": "Silva",
                 "phone": None},
    "billingAddress": ENDERECO, "shippingAddress": {**ENDERECO, "phone": None},
    "lineItems": {"nodes": [{
        "id": "gid://shopify/LineItem/777", "title": "Poltrona Exemplo",
        "name": "Poltrona Exemplo - Azul", "variantTitle": "Azul", "sku": "POLTRONA-001",
        "quantity": 1, "originalUnitPriceSet": _dinheiro("1999.89"),
        "totalDiscountSet": _dinheiro("0.0"),
        "discountAllocations": [_alocacao("150.0", 0)],
        "customAttributes": [{"key": "_impermeabilizacao_123", "value": "Sim [+ R$ 499,99]"},
                             {"key": "_montagem_456", "value": "Não"}],
        "variant": {"id": "gid://shopify/ProductVariant/31", "legacyResourceId": "31",
                    "sku": "POLTRONA-001"},
        "product": {"id": "gid://shopify/Product/987654321", "legacyResourceId": "987654321"},
    }]},
    "shippingLines": {"nodes": [{
        "id": "gid://shopify/ShippingLine/88", "code": "standard", "title": "Entrega padrão",
        "source": "shopify", "originalPriceSet": _dinheiro("39.9"),
        "discountedPriceSet": _dinheiro("39.9"), "discountAllocations": [],
    }]},
    "discountCodes": ["PROMO10"],
    "discountApplications": {"nodes": [{
        "__typename": "DiscountCodeApplication", "index": 0, "targetType": "LINE_ITEM",
        "allocationMethod": "ACROSS", "code": "PROMO10",
        "value": {"__typename": "PricingPercentageValue", "percentage": 7.5},
    }]},
    "transactions": [{
        "id": "gid://shopify/OrderTransaction/9", "kind": "SALE", "status": "SUCCESS",
        "gateway": "appmax_pix", "processedAt": "2026-09-01T12:01:00Z",
        "createdAt": "2026-09-01T12:01:00Z", "amountSet": _dinheiro("1889.79"),
    }],
}


def test_pedido_graphql_vira_o_mesmo_json_rest_do_webhook():
    """O importador so entende o formato REST; campo com nome GraphQL seria ignorado."""
    rest = pedido_graphql_para_rest(NODE)

    assert rest["id"] == 123456789
    assert rest["admin_graphql_api_id"] == "gid://shopify/Order/123456789"
    assert rest["order_number"] == 1001
    assert rest["financial_status"] == "paid"
    assert rest["fulfillment_status"] is None
    assert rest["payment_gateway_names"] == ["appmax_pix"]
    assert rest["total_price"] == "1889.79"
    assert rest["total_shipping_price_set"]["shop_money"]["amount"] == "39.90"
    assert rest["note_attributes"][0] == {"name": "Agendamento", "value": "2026-10-15"}
    assert rest["customer"]["id"] == 55
    assert rest["billing_address"]["province_code"] == "SP"
    assert rest["billing_address"]["country_code"] == "BR"
    assert rest["shipping_address"]["first_name"] == "Maria"
    item = rest["line_items"][0]
    assert item["id"] == 777
    assert item["price"] == "1999.89"
    assert item["product_id"] == 987654321 and item["variant_id"] == 31
    assert item["properties"][0] == {
        "name": "_impermeabilizacao_123", "value": "Sim [+ R$ 499,99]",
    }
    assert item["discount_allocations"][0]["amount"] == "150.00"
    assert rest["shipping_lines"][0]["price"] == "39.90"
    assert rest["shipping_lines"][0]["code"] == "standard"
    assert rest["discount_codes"] == [
        {"code": "PROMO10", "amount": "150.00", "type": "percentage"},
    ]
    assert rest["discount_applications"][0]["value"] == "7.5"
    assert rest["transactions"][0]["kind"] == "sale"


def test_cupom_de_frete_vira_tipo_shipping_e_codigo_sem_aplicacao_entra_zerado():
    """Sem esse mapa, cupom de frete gratis nasceria como desconto em valor no hub."""
    frete = {**NODE["shippingLines"]["nodes"][0],
             "discountAllocations": [_alocacao("39.9", 1)]}
    node = {**NODE, "shippingLines": {"nodes": [frete]},
            "discountCodes": ["FRETE", "SOBRA"], "discountApplications": {"nodes": [{
        "__typename": "DiscountCodeApplication", "index": 1, "targetType": "SHIPPING_LINE",
        "allocationMethod": "EACH", "code": "FRETE",
        "value": {"__typename": "PricingPercentageValue", "percentage": 100.0},
    }]}}

    codigos = pedido_graphql_para_rest(node)["discount_codes"]

    assert codigos == [
        {"code": "FRETE", "amount": "39.90", "type": "shipping"},
        {"code": "SOBRA", "amount": "0.00", "type": "fixed_amount"},
    ]


@pytest.mark.django_db
def test_sincronizacao_de_pedidos_entrega_o_formato_rest_ao_importador(monkeypatch):
    """Passar o node GraphQL cru faria o importador criar pedido vazio (sem itens)."""
    matriz = permissoes.matriz_vazia()
    matriz["receber"]["pedidos"]["get"] = True
    configuracao = ConfiguracaoIntegracao.objects.create(
        nome="Loja", plataforma="shopify", permissoes=matriz,
    )
    recebidos = []

    class ClienteFalso:
        def __init__(self, _configuracao):
            pass

        def contar(self, _recurso):
            return None

        def listar(self, recurso):
            assert recurso == "pedidos"
            return iter([NODE])

    monkeypatch.setattr(sincronizar, "ShopifyClient", ClienteFalso)
    monkeypatch.setitem(
        sincronizar.SINCRONIZADORES, "pedidos", lambda dados: (recebidos.append(dados), True),
    )

    mensagem = sincronizar.sincronizar_loja(configuracao, lambda *_args: None)

    assert recebidos == [pedido_graphql_para_rest(NODE)]
    assert mensagem == "1 itens encontrados; 1 novos cadastros."
