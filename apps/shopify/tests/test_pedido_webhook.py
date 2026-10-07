from decimal import Decimal

import pytest

from apps.core.models import ExternalReference, Origin
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Cliente, ItemPedido, Pedido, Servico
from apps.loja.services.extras_pedido import extras
from apps.loja.services.variantes import criar_produto
from apps.shopify.tests.pedido_exemplo import pedido_shopify, produto_shopify_falso  # noqa: F401
from apps.shopify.webhooks import processar_webhook

pytestmark = pytest.mark.usefixtures("produto_shopify_falso")


def _webhook(operacao, dados, configuracao=None):
    return processar_webhook(configuracao, "pedidos", operacao, dados, lambda *_: None)


@pytest.fixture
def poltrona(db):
    ConfiguracaoIntegracao.objects.create(nome="Shopify", dominio_loja="loja.myshopify.com")
    return criar_produto("Poltrona Exemplo", sku="POLTRONA-001", price=Decimal("1499.90"))


@pytest.mark.django_db
def test_webhook_de_pedido_cria_pedido_completo_com_totais_do_shopify(poltrona):
    """Pedido so com numero e total nao serve ao ERP: falta cliente, item, frete e pagamento."""
    _webhook("create", pedido_shopify())

    pedido = Pedido.objects.get()
    assert pedido.external_number == "1001"
    assert pedido.origin == Origin.SHOPIFY
    assert pedido.cliente == Cliente.objects.get(email="maria@example.com")
    assert ExternalReference.objects.filter(
        entity_type="clientes", external_id="gid://shopify/Customer/777").exists()
    assert pedido.observacao_cliente == "Observação do pedido"
    assert pedido.placed_at.isoformat() == "2026-09-30T13:00:00+00:00"

    cobranca, entrega = pedido.endereco_cobranca, pedido.endereco_entrega
    assert (cobranca.address_line_1, cobranca.number, cobranca.neighborhood) == (
        "Rua das Flores", "100", "Centro")
    assert cobranca.document == "12345678900"
    assert cobranca.metadata["persontype"] == "1"
    assert (entrega.number, entrega.neighborhood, entrega.postal_code) == (
        "100", "Centro", "01000000")

    poltrona_item, almofada = pedido.itens.order_by("id")
    assert poltrona_item.produto == poltrona
    assert poltrona_item.variante == poltrona.variante_padrao
    assert (poltrona_item.quantidade, poltrona_item.subtotal, poltrona_item.total) == (
        1, Decimal("1499.90"), Decimal("1349.91"))
    assert almofada.produto is None
    assert (almofada.nome, almofada.sku, almofada.quantidade) == (
        "Almofada Avulsa", "ALMOFADA-SEM-CADASTRO", 2)
    assert (almofada.subtotal, almofada.total) == (Decimal("100.00"), Decimal("90.00"))

    assert pedido.linhas_frete == [{
        "id": 1, "method_id": "standard", "method_title": "Entrega padrão",
        "total": "39.90", "total_tax": "0.00", "taxes": [], "meta_data": [],
    }]
    assert pedido.shipping_method == "Entrega padrão"
    assert pedido.linhas_cupom == [{
        "id": 1, "code": "PROMO10", "discount": "159.99", "discount_tax": "0.00",
        "meta_data": [],
    }]

    assert (pedido.status, pedido.financial_status) == ("processing", "paid")
    assert pedido.paid_at is not None
    assert (pedido.forma_pagamento, pedido.forma_pagamento_titulo) == ("pix", "appmax_pix")
    pagamento = pedido.pagamentos.get()
    assert (pagamento.transaction_id, pagamento.status) == ("123456789", "paid")
    assert pagamento.amount == pedido.total

    assert pedido.total == Decimal("1479.81")
    assert pedido.total_desconto == Decimal("159.99")
    assert pedido.total_frete == Decimal("39.90")


@pytest.mark.django_db
def test_pedido_do_shopify_guarda_extras_num_unico_metadado_starhub(poltrona):
    """Agendamento, servicos e CPF espalhados em varias chaves ninguem acha depois."""
    _webhook("create", pedido_shopify())

    pedido = Pedido.objects.get()
    item = pedido.itens.get(sku="POLTRONA-001")
    assert [meta["key"] for meta in pedido.metadados] == ["starhub"]
    assert extras(pedido) == {
        "origem": {
            "canal": "shopify", "id": "123456789", "numero": "1001", "nome": "#1001",
            "url": "https://loja.myshopify.com/admin/orders/123456789",
            "status_financeiro": "paid", "atualizado_em": "2026-09-30T15:00:00-03:00",
        },
        "cliente": {"cpf": "12345678900", "tipo_pessoa": "1"},
        "entrega": {"agendamento": "2026-10-15", "tipo": "delivery"},
        "cupons": ["PROMO10"],
        "servicos": [{
            "item_id": item.pk, "sku": "POLTRONA-001",
            "servico": "Impermeabilização da poltrona", "opcao": "Sim", "preco": "499.99",
            # Sem cadastro, o servico nasce na importacao e fica vinculado.
            "servico_id": Servico.objects.get(nome="Impermeabilização da poltrona").pk,
        }],
    }


@pytest.mark.django_db
def test_webhook_de_pedido_repetido_nao_duplica_pedido_nem_itens(poltrona):
    """O Shopify reenvia webhook: cada reenvio nao pode virar pedido ou item novo."""
    _webhook("create", pedido_shopify())
    mensagem = _webhook("create", pedido_shopify())

    assert mensagem == "Registro ja existia."
    assert Pedido.objects.count() == 1
    assert ItemPedido.objects.count() == 2
    pedido = Pedido.objects.get()
    assert pedido.pagamentos.count() == 1
    assert len(pedido.linhas_frete) == 1
    assert len(pedido.metadados) == 1
    assert pedido.total == Decimal("1479.81")


@pytest.mark.django_db
def test_orders_updated_atualiza_status_endereco_e_extras_do_pedido(poltrona):
    """Reembolso e novo endereco no Shopify precisam chegar ao pedido do hub."""
    _webhook("create", pedido_shopify())
    atualizado = pedido_shopify(
        financial_status="refunded",
        updated_at="2026-10-01T09:00:00-03:00",
        note_attributes=[{"name": "Agendamento", "value": "2026-10-20"}],
    )
    atualizado["shipping_address"]["address1"] = "Avenida Brasil, 2000"

    mensagem = _webhook("update", atualizado)

    assert mensagem == "Registro atualizado."
    pedido = Pedido.objects.get()
    assert (pedido.status, pedido.financial_status) == ("refunded", "refunded")
    assert pedido.endereco_entrega.address_line_1 == "Avenida Brasil"
    assert pedido.endereco_entrega.number == "2000"
    assert extras(pedido)["entrega"] == {"agendamento": "2026-10-20", "tipo": "delivery"}
    assert extras(pedido)["origem"]["atualizado_em"] == "2026-10-01T09:00:00-03:00"
    assert ItemPedido.objects.count() == 2
    assert pedido.pagamentos.get().status == "refunded"


@pytest.mark.django_db
def test_orders_updated_de_pedido_desconhecido_sem_permissao_nao_cria(poltrona):
    """Update fora de ordem respeita a permissao de criar desmarcada."""
    mensagem = _webhook("update", pedido_shopify())

    assert mensagem == "Registro nao encontrado."
    assert not Pedido.objects.exists()


@pytest.mark.django_db
def test_pedido_cancelado_no_shopify_fica_cancelado_com_data(poltrona):
    """cancelled_at vale mais que o financial_status: pedido pago e cancelado e cancelado."""
    _webhook("create", pedido_shopify(cancelled_at="2026-09-30T12:00:00-03:00"))

    pedido = Pedido.objects.get()
    assert pedido.status == "cancelled"
    assert pedido.cancelled_at.isoformat() == "2026-09-30T15:00:00+00:00"
