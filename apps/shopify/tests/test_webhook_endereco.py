"""Endereco do webhook: uuid no novo, id inteiro ainda aceito no antigo."""

import json
from unittest.mock import Mock, patch

import pytest

from apps.integracoes.models import ExecucaoIntegracao
from apps.shopify.tests.test_webhooks import _assinatura, _configuracao

pytestmark = pytest.mark.django_db


def _post(client, url):
    corpo = json.dumps({"id": 123}).encode()
    with patch("apps.shopify.views.processar_webhook_shopify.delay",
               return_value=Mock(id="celery-1")):
        return client.post(url, data=corpo, content_type="application/json",
                           HTTP_X_SHOPIFY_HMAC_SHA256=_assinatura(corpo),
                           HTTP_X_SHOPIFY_TOPIC="products/create")


def test_webhook_cadastrado_antes_do_uuid_continua_chegando(client, conta):
    """A Shopify guarda o endereco antigo ate o recadastro: recusar perderia pedidos."""
    configuracao = _configuracao(conta)
    resposta = _post(client, f"/integracoes/shopify/webhook/{configuracao.pk}/produtos/")
    assert resposta.status_code == 202
    assert ExecucaoIntegracao.objects.count() == 1


def test_uuid_de_loja_que_nao_existe_responde_404(client, conta):
    _configuracao(conta)
    url = "/integracoes/shopify/webhook/00000000-0000-0000-0000-000000000000/produtos/"
    assert _post(client, url).status_code == 404
    assert not ExecucaoIntegracao.objects.exists()


def test_webhook_guarda_o_corpo_para_poder_retomar(client, conta):
    """Sem o corpo, um webhook que falhou nao tinha como ser processado de novo."""
    configuracao = _configuracao(conta)
    _post(client, f"/integracoes/shopify/webhook/{configuracao.uuid}/produtos/")
    reenvio = ExecucaoIntegracao.objects.get().parametros["reenvio"]
    assert reenvio == {"recurso": "produtos", "operacao": "create", "dados": {"id": 123}}
