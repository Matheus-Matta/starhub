from decimal import Decimal

import pytest

from apps.core.models import Origin
from apps.loja.models import Cupom, Pedido
from apps.shopify.pedidos import importar_pedido
from apps.shopify.tests.pedido_exemplo import pedido_shopify, produto_shopify_falso  # noqa: F401

pytestmark = pytest.mark.usefixtures("produto_shopify_falso")


@pytest.mark.django_db
def test_cupom_do_pedido_que_o_hub_nao_conhece_e_criado_ativo():
    """Sem o cupom cadastrado o ERP nao sabe explicar o desconto do pedido."""
    importar_pedido(pedido_shopify())

    cupom = Cupom.objects.get(name="PROMO10")
    assert cupom.discount_type == Cupom.TipoDesconto.PERCENTUAL
    assert cupom.value == Decimal("10.00")
    assert cupom.status == Cupom.Status.ATIVO
    assert cupom.origin == Origin.SHOPIFY


@pytest.mark.django_db
def test_cupom_ja_cadastrado_e_reaproveitado_sem_alterar():
    """Cupom criado a mao no hub nao pode ser duplicado nem sobrescrito pelo pedido."""
    Cupom.objects.create(name="PROMO10", value=Decimal("5.00"),
                         discount_type=Cupom.TipoDesconto.VALOR_FIXO)

    importar_pedido(pedido_shopify())

    cupom = Cupom.objects.get()
    assert (cupom.name, cupom.value) == ("PROMO10", Decimal("5.00"))
    assert Pedido.objects.get().linhas_cupom[0]["code"] == "PROMO10"


@pytest.mark.django_db
def test_cupom_sem_discount_codes_vem_de_discount_applications():
    """Pedido editado pode trazer so discount_applications; o desconto nao pode sumir."""
    importar_pedido(pedido_shopify(discount_codes=[]))

    pedido = Pedido.objects.get()
    assert pedido.linhas_cupom[0]["code"] == "PROMO10"
    assert pedido.linhas_cupom[0]["discount"] == "159.99"
    assert Cupom.objects.get().value == Decimal("10.00")


@pytest.mark.django_db
def test_cupom_de_frete_gratis_vira_free_shipping_e_zera_o_frete():
    """Frete gratis do Shopify vem como alocacao na linha de frete, nao no item."""
    dados = pedido_shopify(
        discount_codes=[{"code": "FRETEGRATIS", "amount": "39.90", "type": "shipping"}],
        discount_applications=[{"type": "discount_code", "code": "FRETEGRATIS",
                                "value": "100.0", "value_type": "percentage",
                                "target_type": "shipping_line"}],
        total_price="1599.90",
    )
    for item in dados["line_items"]:
        item["discount_allocations"], item["total_discount"] = [], "0.00"
    dados["shipping_lines"][0]["discount_allocations"] = [{"amount": "39.90"}]

    pedido, criado = importar_pedido(dados)

    assert criado
    assert Cupom.objects.get().discount_type == Cupom.TipoDesconto.FRETE_GRATIS
    assert pedido.linhas_frete[0]["total"] == "0.00"
    assert pedido.total == Decimal("1599.90")


@pytest.mark.django_db
def test_mesmo_pedido_pela_sincronizacao_e_pelo_webhook_vira_um_pedido_so():
    """Sincronizacao manda id numerico e o webhook gid: chaves diferentes duplicariam."""
    sincronizado = pedido_shopify(admin_graphql_api_id=None, transactions=[
        {"kind": "authorization", "status": "success",
         "processed_at": "2026-09-30T10:01:00-03:00"},
        {"kind": "capture", "status": "success", "processed_at": "2026-09-30T11:00:00-03:00"},
    ])
    importar_pedido(sincronizado)
    _pedido, criado = importar_pedido(pedido_shopify(id="gid://shopify/Order/123456789"))

    assert not criado
    pedido = Pedido.objects.get()
    assert pedido.itens.count() == 2
    assert pedido.paid_at.isoformat() == "2026-09-30T14:00:00+00:00"
