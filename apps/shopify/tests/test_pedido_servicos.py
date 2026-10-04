from decimal import Decimal

import pytest

from apps.loja.models import Pedido
from apps.loja.services.extras_pedido import extras, mesclar_extras
from apps.shopify.pedidos_servicos import servicos_do_item
from apps.shopify.pedidos_status import status_do_pedido


def test_servico_pago_vira_servico_com_rotulo_amigavel_e_preco_decimal():
    """O preco "[+ R$ 1.499,99]" em texto brasileiro nao pode virar 1.49999."""
    servicos = servicos_do_item([
        {"name": "_garantia_789", "value": "12 meses [+ R$ 1.499,99]"},
        {"name": "_montagem_456", "value": "Sim (+ R$ 80.00)"},
    ])

    assert servicos == [
        {"servico": "Garantia estendida", "opcao": "12 meses", "preco": Decimal("1499.99")},
        {"servico": "Montagem", "opcao": "Sim", "preco": Decimal("80.00")},
    ]


def test_servico_recusado_vazio_ou_sem_preco_fica_de_fora():
    """"Nao" com preco no nome continua sendo recusa: nao e servico contratado."""
    assert servicos_do_item([
        {"name": "_montagem_456 [+ R$ 80,00]", "value": "Não"},
        {"name": "_embrulho_1", "value": "Sim"},
        {"name": "_tpo_add_by", "value": "app [+ R$ 1,00]"},
        {"name": "", "value": "Sim [+ R$ 1,00]"},
        {"name": "_cor_2", "value": ""},
    ]) == []


@pytest.mark.parametrize(("financeiro", "gateway", "esperado"), [
    ("paid", "pix", "processing"),
    ("partially_paid", "pix", "processing"),
    ("pending", "pix", "pending"),
    ("authorized", "cartao", "pending"),
    ("pending", "Cash on Delivery (COD)", "processing"),
    ("refunded", "pix", "refunded"),
    ("voided", "pix", "cancelled"),
    ("desconhecido", "pix", "pending"),
])
def test_status_do_pedido_segue_a_tabela_do_integrador(financeiro, gateway, esperado):
    """Status errado faz o ERP faturar pedido nao pago (ou segurar pedido pago)."""
    assert status_do_pedido({"financial_status": financeiro}, gateway) == esperado


@pytest.mark.django_db
def test_mesclar_extras_troca_so_a_secao_enviada_e_remove_a_vazia():
    """A API Woo vai gravar uma secao por vez: as outras secoes nao podem sumir."""
    pedido = Pedido.objects.create()
    mesclar_extras(pedido, {"origem": {"canal": "shopify"}, "cupons": ["A"]})
    mesclar_extras(pedido, {"entrega": {"agendamento": "2026-10-15", "tipo": ""},
                            "cupons": []})

    assert extras(pedido) == {
        "origem": {"canal": "shopify"}, "entrega": {"agendamento": "2026-10-15"},
    }
    assert len(pedido.metadados) == 1
