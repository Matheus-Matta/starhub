"""Sincronizacao e webhook de desconto usam o mesmo mapeamento completo do pedido."""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference, Origin
from apps.loja.models import Categoria, Cliente, Cupom
from apps.shopify import atualizar, recursos
from apps.shopify.cupons_vinculo import dados as vinculo_dados

pytestmark = pytest.mark.django_db


def _referenciar(entidade, gid, obj):
    ExternalReference.objects.create(platform=Origin.SHOPIFY, entity_type=entidade,
                                     external_id=gid, object_id=str(obj.pk))


def _frete_gratis(**mudancas):
    desconto = {
        "__typename": "DiscountCodeFreeShipping", "title": "Frete na faixa",
        "summary": "Frete gratis acima de 2 itens", "status": "SCHEDULED",
        "startsAt": "2026-11-01T03:00:00Z", "endsAt": None, "usageLimit": None,
        "appliesOncePerCustomer": False, "asyncUsageCount": 0,
        "codes": {"nodes": [{"code": "FRETE"}, {"code": "FRETE2"}]},
        "combinesWith": {"orderDiscounts": False, "productDiscounts": False,
                         "shippingDiscounts": False},
        "minimumRequirement": {"__typename": "DiscountMinimumQuantity",
                               "greaterThanOrEqualToQuantity": "2"},
        "context": {"__typename": "DiscountCustomers",
                    "customers": [{"id": "gid://shopify/Customer/1"},
                                  {"id": "gid://shopify/Customer/2"}]},
        "maximumShippingPrice": {"amount": "50.0", "currencyCode": "BRL"},
        **mudancas,
    }
    return {"id": "gid://shopify/DiscountCodeNode/77", "codeDiscount": desconto}


def test_sincronizacao_cria_cupom_de_frete_gratis_com_clientes_e_minimo():
    """O cupom sincronizado so com titulo virava "valor fixo ativo" sem regra nenhuma."""
    maria = Cliente.objects.create(email="maria@example.com", nome="Maria")
    _referenciar("clientes", "gid://shopify/Customer/1", maria)

    cupom, criado = recursos.cupom(_frete_gratis())

    assert criado
    assert (cupom.name, cupom.discount_type, cupom.free_shipping) == (
        "Frete na faixa", Cupom.TipoDesconto.FRETE_GRATIS, True)
    assert cupom.status == Cupom.Status.ATIVO
    assert (cupom.minimum_requirement, cupom.minimum_quantity) == (
        Cupom.RequisitoMinimo.QUANTIDADE, 2)
    assert cupom.customer_eligibility == Cupom.ElegibilidadeCliente.CLIENTES
    assert list(cupom.clientes.all()) == [maria]
    assert "shopify" not in cupom.metadata
    shopify = vinculo_dados(cupom)
    assert shopify["status"] == "SCHEDULED"
    assert shopify["frete_maximo"] == "50.00"
    assert shopify["nao_encontrados"] == ["gid://shopify/Customer/2"]
    codigos = ExternalReference.objects.filter(entity_type="cupons_codigos")
    assert sorted(codigos.values_list("external_id", flat=True)) == ["FRETE", "FRETE2"]


def test_webhook_de_atualizacao_reaplica_tudo_no_cupom_vinculado():
    """Atualizar so titulo e status deixava valor, datas e colecoes velhos no hub."""
    cupom, _ = recursos.cupom(_frete_gratis())
    moda = Categoria.objects.create(nome="Moda", slug="moda")
    _referenciar("categorias", "gid://shopify/Collection/5", moda)
    node = _frete_gratis(
        __typename="DiscountCodeBasic", title="Moda 15", status="EXPIRED",
        endsAt="2026-12-01T03:00:00Z", minimumRequirement=None,
        context={"__typename": "DiscountBuyerSelectionAll", "all": "ALL"},
        customerGets={
            "value": {"__typename": "DiscountAmount", "appliesOnEachItem": False,
                      "amount": {"amount": "15.5", "currencyCode": "BRL"}},
            "items": {"__typename": "DiscountCollections",
                      "collections": {"nodes": [{"id": "gid://shopify/Collection/5"}],
                                      "pageInfo": {"hasNextPage": True}}},
        })

    obj, alterou = atualizar.cupom(node)

    assert alterou and obj.pk == cupom.pk
    obj.refresh_from_db()
    assert (obj.name, obj.status, obj.discount_type, obj.value) == (
        "Moda 15", Cupom.Status.EXPIRADO, Cupom.TipoDesconto.VALOR_FIXO, Decimal("15.50"))
    assert (obj.free_shipping, obj.once_per_order) == (False, True)
    assert obj.minimum_requirement == Cupom.RequisitoMinimo.NENHUM
    assert obj.customer_eligibility == Cupom.ElegibilidadeCliente.TODOS
    assert not obj.clientes.exists()
    assert obj.product_eligibility == Cupom.ElegibilidadeProduto.CATEGORIAS
    assert list(obj.categorias.all()) == [moda]
    assert "shopify" not in obj.metadata
    assert vinculo_dados(obj)["listas_incompletas"] is True


def test_webhook_de_desconto_busca_o_desconto_completo_no_shopify(monkeypatch):
    """O corpo do webhook DISCOUNTS_CREATE nao traz codigo, valor nem regras."""
    from apps.integracoes.models import ConfiguracaoIntegracao
    from apps.shopify import cupons
    from apps.shopify.contexto import usando_configuracao
    from apps.shopify.webhooks import processar_webhook

    pedidos = []

    class ClienteFalso:
        def __init__(self, configuracao):
            pass

        def graphql(self, query, variables=None):
            pedidos.append(variables)
            return {"codeDiscountNode": _frete_gratis()}

    monkeypatch.setattr(cupons, "ShopifyClient", ClienteFalso)
    configuracao = ConfiguracaoIntegracao.objects.create(nome="S", dominio_loja="x.myshopify.com")
    corpo = {"admin_graphql_api_id": "gid://shopify/DiscountCodeNode/77",
             "title": "Frete na faixa", "status": "ACTIVE"}

    with usando_configuracao(configuracao):
        processar_webhook(configuracao, "cupons", "create", corpo, lambda *_: None)

    assert pedidos == [{"id": "gid://shopify/DiscountCodeNode/77"}]
    cupom = Cupom.objects.get()
    assert (cupom.discount_type, cupom.minimum_quantity) == (
        Cupom.TipoDesconto.FRETE_GRATIS, 2)
