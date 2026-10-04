"""Envio de cupons e pedidos do hub para o Shopify."""

from datetime import datetime, timezone

import pytest

from apps.core.models import Address, ExternalReference
from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.loja.models import Cupom, Pedido
from apps.shopify.envio.cupons import CupomShopify
from apps.shopify.envio.pedidos import PedidoShopify
from apps.shopify.tests.envio_falso import enviador

pytestmark = pytest.mark.django_db
OK = {"userErrors": []}
GID = "gid://shopify/DiscountCodeNode/55"
ATIVO = {"codeDiscount": {"status": "ACTIVE"}}


def cupom(**campos):
    base = {"name": "Promo", "discount_type": Cupom.TipoDesconto.PERCENTUAL, "value": 10,
            "status": Cupom.Status.ATIVO}
    return Cupom.objects.create(**{**base, **campos})


def _vinculo(c, metadata):
    return ExternalReference.objects.create(
        platform="shopify", entity_type="cupons", external_id=GID, object_id=str(c.pk),
        metadata=metadata)


def test_cupom_criar_nao_suportado():
    """Cupom do hub tem codigo interno aleatorio: o cliente nao teria o que digitar."""
    env, falso = enviador(CupomShopify)
    with pytest.raises(EnvioNaoSuportado):
        env.criar(cupom())
    assert falso.chamadas == []


def test_cupom_atualizar_nunca_envia_o_codigo():
    """Mudar o codigo no Shopify quebraria a campanha do lojista."""
    c = cupom(usage_limit=5, usage_limit_per_customer=1,
              ends_at=datetime(2026, 12, 1, tzinfo=timezone.utc))
    env, falso = enviador(CupomShopify, discountCodeBasicUpdate=OK,
                          codeDiscountNode=ATIVO)
    env.atualizar(c, GID)
    query, variaveis = falso.chamadas[1]
    assert "discountCodeBasicUpdate" in query and len(falso.chamadas) == 2
    desconto = variaveis["desconto"]
    assert "code" not in desconto
    assert desconto["title"] == "Promo" and desconto["usageLimit"] == 5
    assert desconto["appliesOncePerCustomer"] is True
    assert desconto["endsAt"].startswith("2026-12-01")


def test_cupom_sem_termino_manda_ends_at_nulo():
    """None precisa ir explicito, senao o Shopify mantem a data antiga."""
    env, falso = enviador(CupomShopify, discountCodeBasicUpdate=OK, codeDiscountNode=ATIVO)
    env.atualizar(cupom(), GID)
    assert falso.chamadas[1][1]["desconto"]["endsAt"] is None


def test_cupom_frete_gratis_usa_a_mutation_de_frete():
    c = cupom(discount_type=Cupom.TipoDesconto.FRETE_GRATIS, value=0)
    env, falso = enviador(CupomShopify, discountCodeFreeShippingUpdate=OK, codeDiscountNode=ATIVO)
    env.atualizar(c, GID)
    assert "discountCodeFreeShippingUpdate" in falso.chamadas[1][0]


def test_cupom_pausado_atualiza_e_depois_desativa():
    """Desativar depois do update: o update reescreveria o endsAt que a desativacao fixa."""
    env, falso = enviador(CupomShopify, discountCodeBasicUpdate=OK, discountCodeDeactivate=OK,
                          codeDiscountNode=ATIVO)
    env.atualizar(cupom(status=Cupom.Status.PAUSADO), GID)
    assert "discountCodeBasicUpdate" in falso.chamadas[1][0]
    assert "discountCodeDeactivate" in falso.chamadas[2][0]


def test_cupom_ativo_que_esta_expirado_no_shopify_ativa_antes_do_update():
    env, falso = enviador(CupomShopify, discountCodeBasicUpdate=OK, discountCodeActivate=OK,
                          codeDiscountNode={"codeDiscount": {"status": "EXPIRED"}})
    env.atualizar(cupom(), GID)
    assert "discountCodeActivate" in falso.chamadas[1][0]
    assert "discountCodeBasicUpdate" in falso.chamadas[2][0]


def test_cupom_de_tipo_que_o_hub_nao_edita_e_ignorado():
    c = cupom()
    _vinculo(c, {"tipo": "DiscountCodeBxgy"})
    env, falso = enviador(CupomShopify)
    with pytest.raises(EnvioNaoSuportado):
        env.atualizar(c, GID)
    assert falso.chamadas == []


def test_cupom_excluir_chama_discount_code_delete():
    env, falso = enviador(CupomShopify, discountCodeDelete=OK)
    env.excluir(GID)
    assert falso.chamadas[0][1] == {"id": GID}


def test_pedido_criar_e_excluir_nao_suportados():
    env, _ = enviador(PedidoShopify)
    with pytest.raises(EnvioNaoSuportado):
        env.criar(Pedido())
    with pytest.raises(EnvioNaoSuportado):
        env.excluir("1")


def test_pedido_atualizar_manda_nota_email_e_endereco():
    entrega = Address.objects.create(
        recipient_name="Ana Maria Lima", address_line_1="Rua A", number="10",
        neighborhood="Centro", city="Sao Paulo", state_code="SP", postal_code="01000-000",
        country_code="BR")
    pedido = Pedido.objects.create(notas="Entregar de manha", email="a@x.com",
                                   endereco_entrega=entrega)
    env, falso = enviador(PedidoShopify, orderUpdate=OK)
    env.atualizar(pedido, "99")
    entrada = falso.chamadas[0][1]["input"]
    assert entrada["id"] == "gid://shopify/Order/99"
    assert entrada["note"] == "Entregar de manha" and entrada["email"] == "a@x.com"
    endereco = entrada["shippingAddress"]
    assert endereco["address1"] == "Rua A, 10" and endereco["address2"] == "Centro"
    assert endereco["firstName"] == "Ana" and endereco["lastName"] == "Maria Lima"
    assert endereco["provinceCode"] == "SP" and endereco["countryCode"] == "BR"


def test_pedido_sem_endereco_nao_manda_shipping_address():
    """Mandar endereco vazio apagaria o endereco de entrega que existe no Shopify."""
    env, falso = enviador(PedidoShopify, orderUpdate=OK)
    env.atualizar(Pedido.objects.create(notas="x"), "99")
    assert "shippingAddress" not in falso.chamadas[0][1]["input"]


def test_endereco_sem_pais_e_com_telefone_local_nao_derruba_o_order_update():
    """countryCode e enum e phone e E.164 no MailingAddressInput: "" ou "(11) 9..." fazem
    o Shopify recusar a mutation inteira, e a nota/e-mail tambem nao chegariam."""
    entrega = Address.objects.create(address_line_1="Rua A", phone="(11) 98888-7777")
    pedido = Pedido.objects.create(endereco_entrega=entrega)
    env, falso = enviador(PedidoShopify, orderUpdate=OK)
    env.atualizar(pedido, "99")
    endereco = falso.chamadas[0][1]["input"]["shippingAddress"]
    assert "countryCode" not in endereco and "provinceCode" not in endereco
    assert endereco["phone"] == "+5511988887777"
    entrega.phone = "123"
    entrega.save()
    env.atualizar(Pedido.objects.get(pk=pedido.pk), "99")
    assert "phone" not in falso.chamadas[1][1]["input"]["shippingAddress"]
