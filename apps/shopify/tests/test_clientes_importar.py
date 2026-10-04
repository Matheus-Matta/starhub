"""Importacao completa do cliente Shopify: enderecos, marketing, pagante e vinculo.

Antes so entravam e-mail, nome e telefone: o cliente chegava sem endereco e sem a
marca de que ja comprou, e o ERP via um cadastro pela metade.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from apps.core.models import Address, ExternalReference
from apps.loja.models import Cliente, ClienteEndereco, Pedido
from apps.loja.services.clientes import endereco_do_cliente
from apps.shopify import atualizar, recursos
from apps.shopify.tests import cliente_exemplo

pytestmark = pytest.mark.django_db

SEM_COMPRA = {"numberOfOrders": "0", "amountSpent": {"amount": "0.0", "currencyCode": "BRL"}}


def _vinculo():
    return ExternalReference.objects.get(entity_type="clientes", external_id=cliente_exemplo.GID)


def test_cliente_com_dois_enderecos_importa_os_dois_com_o_padrao_certo():
    """O defaultAddress do Shopify vira o padrao; o outro endereco tambem entra."""
    cliente, criado = recursos.cliente(cliente_exemplo.graphql())

    assert criado is True
    entregas = ClienteEndereco.objects.filter(cliente=cliente, tipo="shipping")
    assert entregas.count() == 2
    padrao = endereco_do_cliente(cliente, "shipping")
    assert (padrao.address_line_1, padrao.number, padrao.neighborhood) == (
        "Av. Norte", "55", "Casa Amarela")
    assert (padrao.postal_code, padrao.state_code, padrao.country_code) == ("52070000", "PE", "BR")
    assert padrao.recipient_name == "Ana Souza"
    assert endereco_do_cliente(cliente, "billing").address_line_1 == "Av. Norte"


def test_campos_do_cliente_vem_do_shopify():
    cliente, _ = recursos.cliente(cliente_exemplo.graphql())

    assert cliente.email == "ana@exemplo.com"
    assert cliente.telefone == "5581988887777"
    assert cliente.notas == "Cliente VIP"
    assert cliente.aceita_marketing is True
    assert cliente.locale == "pt-BR"
    assert cliente.empresa == "Ana ME"
    cliente.refresh_from_db()
    assert cliente.created_at == datetime(2024, 3, 10, 12, 0, tzinfo=UTC)


def test_dados_so_do_shopify_ficam_no_vinculo():
    """Contadores, tags e estado da conta nao tem coluna no hub: ficam no vinculo."""
    recursos.cliente(cliente_exemplo.graphql())

    metadata = _vinculo().metadata
    assert metadata["numberOfOrders"] == 3
    assert metadata["amountSpent"] == {"amount": "250.40", "currencyCode": "BRL"}
    assert metadata["tags"] == ["vip", "atacado"]
    assert metadata["state"] == "ENABLED"


def test_reimportar_nao_duplica_endereco():
    recursos.cliente(cliente_exemplo.graphql())
    enderecos = Address.objects.count()

    cliente, criado = recursos.cliente(cliente_exemplo.graphql())

    assert criado is False
    assert Address.objects.count() == enderecos
    assert ClienteEndereco.objects.filter(cliente=cliente).count() == 3


def test_endereco_alterado_no_shopify_atualiza():
    recursos.cliente(cliente_exemplo.graphql())
    dados = cliente_exemplo.graphql()
    casa = dados["addressesV2"]["nodes"][0]
    casa.update({"address1": "Rua Nova, 9", "address2": None, "zip": "50000-000"})

    cliente, alterou = atualizar.cliente(dados)

    assert alterou is True
    vinculo = ExternalReference.objects.get(
        entity_type="enderecos_cliente", external_id="gid://shopify/MailingAddress/11")
    endereco = Address.objects.get(pk=vinculo.object_id)
    assert (endereco.address_line_1, endereco.number) == ("Rua Nova", "9")
    assert (endereco.address_line_2, endereco.postal_code) == ("", "50000000")
    assert ClienteEndereco.objects.filter(cliente=cliente, tipo="shipping").count() == 2


def test_padrao_trocado_no_shopify_troca_o_padrao_do_hub():
    recursos.cliente(cliente_exemplo.graphql())
    dados = cliente_exemplo.graphql()
    dados["defaultAddress"] = dados["addressesV2"]["nodes"][0]

    cliente, _ = atualizar.cliente(dados)

    assert endereco_do_cliente(cliente, "shipping").address_line_1 == "Rua das Flores"
    assert endereco_do_cliente(cliente, "billing").address_line_1 == "Rua das Flores"
    assert ClienteEndereco.objects.filter(cliente=cliente, tipo="billing").count() == 1


def test_cliente_com_pedidos_no_shopify_vira_pagante():
    cliente, _ = recursos.cliente(cliente_exemplo.graphql())

    assert cliente.cliente_pagante is True


def test_cliente_sem_compra_no_shopify_nao_vira_pagante():
    cliente, _ = recursos.cliente(cliente_exemplo.graphql(**SEM_COMPRA))

    assert cliente.cliente_pagante is False


def test_cliente_com_pedido_pago_no_hub_vira_pagante():
    """O e-mail casa com um cliente do hub que ja tem pedido pago."""
    hub = Cliente.objects.create(email="ana@exemplo.com", nome="Ana")
    Pedido.objects.create(cliente=hub, status=Pedido.Status.PROCESSANDO, total=Decimal("10.00"))

    cliente, criado = recursos.cliente(cliente_exemplo.graphql(**SEM_COMPRA))

    assert (cliente.pk, criado) == (hub.pk, False)
    assert cliente.cliente_pagante is True


def test_pagante_nunca_volta_a_falso():
    """Shopify sem compra (pedido apagado, outra loja) nao apaga o que o hub ja sabe."""
    recursos.cliente(cliente_exemplo.graphql())

    cliente, _ = atualizar.cliente(cliente_exemplo.graphql(**SEM_COMPRA))

    cliente.refresh_from_db()
    assert cliente.cliente_pagante is True


def test_telefone_invalido_nao_derruba_a_importacao():
    """Cliente.save recusa telefone fora de 8 a 15 digitos: o import inteiro caia."""
    dados = cliente_exemplo.graphql(defaultPhoneNumber={"phoneNumber": "123"})
    dados["defaultAddress"]["phone"] = "abc"

    cliente, _ = recursos.cliente(dados)

    assert cliente.telefone == ""
    assert endereco_do_cliente(cliente, "shipping").phone == ""


def test_cliente_do_hub_achado_pelo_email_mantem_o_que_ja_tinha():
    """O cadastro do hub vem primeiro: a importacao so completa o que esta vazio."""
    Cliente.objects.create(email="ana@exemplo.com", nome="Ana Maria", telefone="81911112222")

    cliente, _ = recursos.cliente(cliente_exemplo.graphql())

    assert (cliente.nome, cliente.telefone) == ("Ana Maria", "81911112222")
    assert cliente.notas == "Cliente VIP"
    assert ClienteEndereco.objects.filter(cliente=cliente, tipo="shipping").count() == 2


def test_pedido_nao_pago_no_shopify_nao_faz_pagante():
    """numberOfOrders conta boleto vencido; com amountSpent zero o cliente nao pagou."""
    dados = cliente_exemplo.graphql(numberOfOrders="2",
                                    amountSpent={"amount": "0.0", "currencyCode": "BRL"})

    cliente, _ = recursos.cliente(dados)

    assert cliente.cliente_pagante is False
