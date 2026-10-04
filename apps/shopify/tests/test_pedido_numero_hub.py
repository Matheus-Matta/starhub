"""Numero do pedido e sempre do hub; o do Shopify (#1001) fica em external_number."""

import re
from decimal import Decimal

import pytest

from apps.core.models import ExternalReference, Origin
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Pedido
from apps.loja.services.variantes import criar_produto
from apps.shopify import pedidos
from apps.shopify.tests.pedido_exemplo import pedido_shopify, produto_shopify_falso  # noqa: F401
from apps.shopify.webhooks import processar_webhook
from apps.woo_api.recursos.pedidos_saida import pedido_para_woo

pytestmark = pytest.mark.usefixtures("produto_shopify_falso")
NUMERO_DO_HUB = re.compile(r"^SH-[0-9A-F]{10}$")
GID = "gid://shopify/Order/123456789"


def _webhook(operacao, dados):
    return processar_webhook(None, "pedidos", operacao, dados, lambda *_: None)


@pytest.fixture
def poltrona(db):
    ConfiguracaoIntegracao.objects.create(nome="Shopify", dominio_loja="loja.myshopify.com")
    return criar_produto("Poltrona Exemplo", sku="POLTRONA-001", price=Decimal("1499.90"))


@pytest.mark.django_db
def test_pedido_do_shopify_ganha_numero_do_hub_e_guarda_o_da_loja(poltrona):
    """Com o numero da loja em number, dois marketplaces com #1001 brigavam pelo indice."""
    _webhook("create", pedido_shopify())

    pedido = Pedido.objects.get()
    assert NUMERO_DO_HUB.match(pedido.number), pedido.number
    assert pedido.external_number == "1001"


@pytest.mark.django_db
def test_numero_igual_de_outra_origem_nao_e_tocado_nem_muda_o_numero_novo(poltrona):
    """Antes virava "SHOPIFY-<id>"; agora o numero do hub nunca depende do da loja."""
    do_hub = Pedido.objects.create(number="1001", origin=Origin.STARHUB)

    _webhook("create", pedido_shopify())

    importado = Pedido.objects.exclude(pk=do_hub.pk).get()
    assert NUMERO_DO_HUB.match(importado.number)
    assert importado.external_number == "1001"
    do_hub.refresh_from_db()
    assert (do_hub.number, do_hub.external_number) == ("1001", "")


@pytest.mark.django_db
def test_reenvio_acha_o_pedido_pelo_vinculo_e_mantem_o_numero(poltrona):
    """Casar pelo numero da loja nao funciona mais: o vinculo e quem acha o pedido."""
    _webhook("create", pedido_shopify())
    numero = Pedido.objects.get().number

    _webhook("update", pedido_shopify(note="mudou"))

    pedido = Pedido.objects.get()
    assert pedido.number == numero
    assert pedido.observacao_cliente == "mudou"


@pytest.mark.django_db
def test_pedido_antigo_sem_vinculo_e_achado_pela_referencia_na_origem(poltrona):
    """Pedido gravado antes do vinculo existir seria duplicado no proximo webhook."""
    antigo = Pedido.objects.create(
        origin=Origin.SHOPIFY, source_name="shopify", source_reference=GID,
    )

    _webhook("create", pedido_shopify())

    assert list(Pedido.objects.values_list("pk", flat=True)) == [antigo.pk]
    assert ExternalReference.objects.get(entity_type="pedidos").object_id == str(antigo.pk)


@pytest.mark.django_db
def test_dois_webhooks_ao_mesmo_tempo_nao_criam_dois_pedidos(poltrona, monkeypatch):
    """Sem o indice do numero, quem segura o segundo e o indice unico do vinculo."""
    _webhook("create", pedido_shopify())
    primeiro = Pedido.objects.get()
    # O segundo webhook leu "sem vinculo" antes do primeiro gravar o dele.
    monkeypatch.setattr(pedidos, "_existente", lambda *_args: None)
    monkeypatch.setattr(pedidos, "_pelo_rastro", lambda _externo: None)

    _webhook("create", pedido_shopify())

    assert list(Pedido.objects.values_list("pk", flat=True)) == [primeiro.pk]


@pytest.mark.django_db
def test_api_woo_devolve_o_numero_do_hub_e_o_da_loja_no_starhub(poltrona):
    """O ERP precisa do numero do hub em "number" e do da loja para conferir no Shopify."""
    _webhook("create", pedido_shopify())

    corpo = pedido_para_woo(Pedido.objects.get())

    assert corpo["number"] == str(corpo["id"])
    starhub = next(m["value"] for m in corpo["meta_data"] if m["key"] == "starhub")
    assert (starhub["origem"]["numero"], starhub["origem"]["nome"]) == ("1001", "#1001")
