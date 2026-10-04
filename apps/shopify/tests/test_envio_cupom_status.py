"""Ativar/desativar cupom no Shopify espelha o hub e so age se o estado atual difere."""

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Cupom
from apps.shopify.cliente import ShopifyErro
from apps.shopify.envio.cupons import CupomShopify
from apps.shopify.tests.envio_falso import enviador

pytestmark = pytest.mark.django_db
OK = {"userErrors": []}
GID = "gid://shopify/DiscountCodeNode/55"


def cupom(**campos):
    base = {"name": "Promo", "discount_type": Cupom.TipoDesconto.PERCENTUAL, "value": 10,
            "status": Cupom.Status.ATIVO}
    return Cupom.objects.create(**{**base, **campos})


def vinculo(c, metadata=None):
    return ExternalReference.objects.create(
        platform="shopify", entity_type="cupons", external_id=GID, object_id=str(c.pk),
        metadata=metadata or {})


def no_shopify(status):
    return {"codeDiscount": {"status": status}}


def enviar(c, status_shopify):
    # codeDiscountNode por ultimo: o texto das mutations tambem o contem e o falso
    # devolve a primeira chave que casa.
    env, falso = enviador(CupomShopify, discountCodeBasicUpdate=OK, discountCodeActivate=OK,
                          discountCodeDeactivate=OK, codeDiscountNode=no_shopify(status_shopify))
    env.atualizar(c, GID)
    return [q for q, _ in falso.chamadas]


def mutations(chamadas):
    return [nome for q in chamadas for nome in ("Activate", "Deactivate", "BasicUpdate")
            if f"discountCode{nome}(" in q]


def test_pausado_no_hub_e_ja_desativado_no_shopify_nao_chama_deactivate():
    """Deactivate em desconto ja desativado volta userErrors e o envio viraria Falhou."""
    chamadas = enviar(cupom(status=Cupom.Status.PAUSADO), "EXPIRED")
    assert mutations(chamadas) == ["BasicUpdate"]


def test_pausado_no_hub_e_ativo_no_shopify_desativa_depois_do_update():
    chamadas = enviar(cupom(status=Cupom.Status.PAUSADO), "ACTIVE")
    assert mutations(chamadas) == ["BasicUpdate", "Deactivate"]


def test_pausado_no_hub_e_agendado_no_shopify_desativa():
    assert "Deactivate" in mutations(enviar(cupom(status=Cupom.Status.PAUSADO), "SCHEDULED"))


def test_ativo_no_hub_e_expirado_no_shopify_ativa_antes_do_update():
    chamadas = enviar(cupom(), "EXPIRED")
    assert mutations(chamadas) == ["Activate", "BasicUpdate"]


def test_ativo_no_hub_e_ativo_no_shopify_nao_ativa_nem_desativa():
    assert mutations(enviar(cupom(), "ACTIVE")) == ["BasicUpdate"]


def test_anotacao_velha_nao_decide_nada():
    """A anotacao de status e da importacao: o que vale e o status de agora no Shopify."""
    velha = cupom()
    vinculo(velha, {"status": "ACTIVE"})
    assert mutations(enviar(velha, "EXPIRED")) == ["Activate", "BasicUpdate"]
    velha = cupom(name="Outra", status=Cupom.Status.PAUSADO)
    vinculo_b = ExternalReference.objects.create(
        platform="shopify", entity_type="cupons", external_id=GID + "9",
        object_id=str(velha.pk), metadata={"status": "ACTIVE"})
    assert mutations(enviar(velha, "EXPIRED")) == ["BasicUpdate"]
    vinculo_b.refresh_from_db()
    assert vinculo_b.metadata["status"] == "EXPIRED"


def test_vinculo_guarda_o_status_real_e_preserva_o_resto():
    c = cupom(status=Cupom.Status.PAUSADO)
    ref = vinculo(c, {"tipo": "DiscountCodeBasic", "status": "ACTIVE"})
    enviar(c, "ACTIVE")
    ref.refresh_from_db()
    assert ref.metadata == {"tipo": "DiscountCodeBasic", "status": "EXPIRED"}
    assert "shopify" not in Cupom.objects.get(pk=c.pk).metadata
    outro = cupom(name="B")
    ref = ExternalReference.objects.create(platform="shopify", entity_type="cupons",
                                           external_id=GID + "8", object_id=str(outro.pk))
    enviar(outro, "EXPIRED")
    ref.refresh_from_db()
    assert ref.metadata["status"] == "ACTIVE"
    enviar(outro, "ACTIVE")
    ref.refresh_from_db()
    assert ref.metadata["status"] == "ACTIVE"


def test_desconto_sem_status_no_shopify_nao_manda_nada():
    env, falso = enviador(CupomShopify, codeDiscountNode={"codeDiscount": None})
    with pytest.raises(ShopifyErro):
        env.atualizar(cupom(), GID)
    assert len(falso.chamadas) == 1
