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

    assert "Shopify webhook rejeitado (401)" in caplog.text
    assert "HMAC diferente" in caplog.text
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

    assert "Dado privado" not in caplog.text
    assert "hmac-privado" not in caplog.text
    assert "motivo=HMAC diferente" in caplog.text


@pytest.mark.django_db
@override_settings(DEBUG=False, LOG_CORPO_INTEGRACOES=False)
def test_401_em_producao_diz_quando_o_segredo_do_app_esta_vazio(client, conta, caplog):
    """Em prod o 401 saia sem log: nao dava para saber se o segredo faltava ou estava
    errado na configuracao que a Shopify ainda chamava."""
    configuracao = ConfiguracaoIntegracao.objects.create(
        account=conta, nome="Loja antiga", plataforma="shopify")
    url = f"/integracoes/shopify/webhook/{configuracao.uuid}/clientes/"

    with caplog.at_level(logging.INFO, logger="django.request"):
        resposta = client.post(url, data=b"{}", content_type="application/json",
                               HTTP_X_SHOPIFY_HMAC_SHA256="x",
                               HTTP_X_SHOPIFY_SHOP_DOMAIN="antiga.myshopify.com")

    assert resposta.status_code == 401
    assert "segredo do app vazio" in caplog.text
    assert "antiga.myshopify.com" in caplog.text


@pytest.mark.django_db
@override_settings(DEBUG=False, LOG_CORPO_INTEGRACOES=True)
def test_webhook_valido_mostra_o_corpo_em_producao_com_a_chave_ligada(client, conta, caplog):
    """Com LOG_CORPO_INTEGRACOES=1 o corpo aparece em prod, mas credencial sai mascarada."""
    configuracao = _configuracao(conta)
    url = f"/integracoes/shopify/webhook/{configuracao.uuid}/produtos/"
    corpo = b'{"id": 123, "title": "Camiseta azul", "access_token": "shpat_segredo"}'

    with caplog.at_level(logging.INFO, logger="django.request"):
        resposta = client.post(url, data=corpo, content_type="application/json",
                               HTTP_X_SHOPIFY_HMAC_SHA256=_hmac(corpo),
                               HTTP_X_SHOPIFY_TOPIC="products/update")

    assert resposta.status_code in (202, 204)
    assert "Shopify webhook recebido" in caplog.text
    assert "Camiseta azul" in caplog.text
    assert "shpat_segredo" not in caplog.text


@pytest.mark.django_db
@override_settings(DEBUG=False, LOG_CORPO_INTEGRACOES=False)
def test_webhook_valido_sem_a_chave_loga_so_o_tamanho(client, conta, caplog):
    configuracao = _configuracao(conta)
    url = f"/integracoes/shopify/webhook/{configuracao.uuid}/produtos/"
    corpo = b'{"title": "Dado privado"}'

    with caplog.at_level(logging.INFO, logger="django.request"):
        client.post(url, data=corpo, content_type="application/json",
                    HTTP_X_SHOPIFY_HMAC_SHA256=_hmac(corpo),
                    HTTP_X_SHOPIFY_TOPIC="products/update")

    assert "Shopify webhook recebido" in caplog.text
    assert f"<{len(corpo)} bytes" in caplog.text
    assert "Dado privado" not in caplog.text
