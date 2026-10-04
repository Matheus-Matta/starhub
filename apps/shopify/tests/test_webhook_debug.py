import base64
import hashlib
import hmac
import logging

import pytest
from django.test import override_settings

from apps.integracoes.models import ConfiguracaoIntegracao


def _configuracao(conta):
    configuracao = ConfiguracaoIntegracao.objects.create(
        account=conta, nome="Shopify", plataforma="shopify"
    )
    configuracao.segredo_app = "segredo-webhook"
    configuracao.save()
    return configuracao


def _hmac(corpo):
    resumo = hmac.new(b"segredo-webhook", corpo, hashlib.sha256).digest()
    return base64.b64encode(resumo).decode()


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_webhook_exibe_hmac_json_e_diagnostico_no_terminal_em_dev(client, conta, caplog):
    """Em dev, a comparacao completa precisa explicar uma assinatura rejeitada."""
    configuracao = _configuracao(conta)
    url = f"/integracoes/shopify/webhook/{configuracao.uuid}/produtos/"
    corpo = b'{"id": 123, "title": "Camiseta azul"}'

    with caplog.at_level(logging.INFO, logger="django.request"):
        client.post(
            url,
            data=corpo,
            content_type="application/json",
            HTTP_X_SHOPIFY_HMAC_SHA256="hmac-enviado-pela-shopify",
            HTTP_X_SHOPIFY_TOPIC="products/update",
            HTTP_X_SHOPIFY_SHOP_DOMAIN="loja-teste.myshopify.com",
            HTTP_X_SHOPIFY_WEBHOOK_ID="entrega-123",
        )

    assert "Shopify webhook recebido (DEV)" in caplog.text
    assert "Camiseta azul" in caplog.text
    assert "hmac_recebido=hmac-enviado-pela-shopify" in caplog.text
    assert f"hmac_calculado={_hmac(corpo)}" in caplog.text
    assert f"corpo_bytes={len(corpo)}" in caplog.text
    assert f"corpo_sha256={hashlib.sha256(corpo).hexdigest()}" in caplog.text


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_webhook_nao_exibe_diagnostico_no_terminal_em_producao(client, conta, caplog):
    """Payload e HMAC nao podem aparecer nos logs quando DEBUG estiver desligado."""
    configuracao = _configuracao(conta)
    url = f"/integracoes/shopify/webhook/{configuracao.uuid}/produtos/"

    with caplog.at_level(logging.INFO, logger="django.request"):
        client.post(
            url,
            data=b'{"title": "Dado privado"}',
            content_type="application/json",
            HTTP_X_SHOPIFY_HMAC_SHA256="hmac-privado",
        )

    assert "Shopify webhook recebido (DEV)" not in caplog.text
    assert "Dado privado" not in caplog.text
    assert "hmac-privado" not in caplog.text
