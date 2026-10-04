import base64
import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from apps.core.models import ExternalReference, Origin
from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.loja.models import Produto
from apps.loja.services.variantes import criar_produto
from apps.shopify.views import OPERACOES_TOPICO
from apps.shopify.webhooks import processar_webhook


def _configuracao(conta, habilitado=True):
    matriz = permissoes.matriz_vazia()
    matriz["receber"]["produtos"]["create"] = habilitado
    configuracao = ConfiguracaoIntegracao.objects.create(
        account=conta,
        nome="Shopify",
        plataforma="shopify",
        permissoes=matriz,
    )
    configuracao.segredo_app = "segredo-webhook"
    configuracao.save()
    return configuracao


def _assinatura(corpo):
    resumo = hmac.new(b"segredo-webhook", corpo, hashlib.sha256).digest()
    return base64.b64encode(resumo).decode()


def test_topico_updated_do_shopify_usa_permissao_atualizar():
    """Orders usa 'updated', mas a matriz comum deve continuar usando 'update'."""
    assert OPERACOES_TOPICO["updated"] == "update"


@pytest.mark.django_db
def test_update_de_produto_altera_somente_preco_promocao_e_estoque():
    """Webhook de produto nao pode sobrescrever nome nem criar outro cadastro."""
    produto = criar_produto(
        "Nome do StarHub", sku="SKU-1", price=Decimal("50.00"), inventory_quantity=2
    )
    ExternalReference.objects.create(
        platform=Origin.SHOPIFY,
        entity_type="produtos",
        external_id="gid://shopify/Product/123",
        object_id=str(produto.pk),
    )
    dados = {
        "id": 123,
        "title": "Nome que nao deve entrar",
        "variants": [{
            "sku": "SKU-1",
            "price": "80.00",
            "compare_at_price": "100.00",
            "inventory_quantity": 7,
        }],
    }

    mensagem = processar_webhook(None, "produtos", "update", dados, lambda *_: None)

    produto.refresh_from_db()
    variante = produto.variante_padrao
    variante.refresh_from_db()
    assert produto.nome == "Nome do StarHub"
    assert variante.price == Decimal("100.00")
    assert variante.sale_price == Decimal("80.00")
    assert variante.inventory_quantity == 7
    assert mensagem == "Registro atualizado."


@pytest.mark.django_db
def test_update_de_produto_inexistente_nao_cria_quando_create_desabilitado(conta):
    """Update fora de ordem deve respeitar a permissao de criacao desmarcada."""
    configuracao = _configuracao(conta, habilitado=False)
    mensagem = processar_webhook(
        configuracao, "produtos", "update", {"id": 999, "title": "Novo"}, lambda *_: None
    )

    assert not Produto.objects.exists()
    assert mensagem == "Registro nao encontrado."


@pytest.mark.django_db
def test_update_de_produto_inexistente_cria_quando_create_habilitado(conta):
    """Perder o evento create nao pode deixar o item ausente se criar estiver ativo."""
    configuracao = _configuracao(conta, habilitado=True)
    dados = {
        "id": 999,
        "title": "Produto recebido por update",
        "handle": "produto-update",
        "variants": [{
            "sku": "SKU-UPDATE",
            "price": "80.00",
            "compare_at_price": "100.00",
            "inventory_quantity": 7,
        }],
    }

    mensagem = processar_webhook(
        configuracao, "produtos", "update", dados, lambda *_: None
    )

    produto = Produto.objects.get()
    variante = produto.variante_padrao
    assert produto.nome == "Produto recebido por update"
    assert variante.sku == "SKU-UPDATE"
    assert variante.price == Decimal("100.00")
    assert variante.sale_price == Decimal("80.00")
    assert variante.inventory_quantity == 7
    assert ExternalReference.objects.filter(
        platform=Origin.SHOPIFY,
        entity_type="produtos",
        external_id="gid://shopify/Product/999",
        object_id=str(produto.pk),
    ).exists()
    assert mensagem == "Registro criado a partir da atualizacao."


@pytest.mark.django_db
def test_webhook_valido_enfileira_processamento_e_responde_rapido(client, conta):
    """O Shopify nao pode esperar a importacao terminar dentro da requisicao."""
    configuracao = _configuracao(conta)
    corpo = json.dumps({"id": 123, "title": "Camiseta"}).encode()
    url = f"/integracoes/shopify/webhook/{configuracao.uuid}/produtos/"
    resultado = Mock(id="celery-webhook-1")

    with patch(
        "apps.shopify.views.processar_webhook_shopify.delay", return_value=resultado
    ) as delay:
        resposta = client.post(
            url,
            data=corpo,
            content_type="application/json",
            HTTP_X_SHOPIFY_HMAC_SHA256=_assinatura(corpo),
            HTTP_X_SHOPIFY_TOPIC="products/create",
        )

    assert resposta.status_code == 202
    execucao = ExecucaoIntegracao.objects.get()
    assert execucao.tipo == ExecucaoIntegracao.Tipo.RECEBER
    assert execucao.celery_task_id == "celery-webhook-1"
    delay.assert_called_once_with(
        str(execucao.pk), "produtos", "create", {"id": 123, "title": "Camiseta"}
    )


@pytest.mark.django_db
def test_webhook_rejeita_assinatura_invalida(client, conta):
    """Uma chamada forjada nao pode criar tarefa nem alterar os dados da loja."""
    configuracao = _configuracao(conta)
    url = f"/integracoes/shopify/webhook/{configuracao.uuid}/produtos/"

    resposta = client.post(
        url,
        data=b"{}",
        content_type="application/json",
        HTTP_X_SHOPIFY_HMAC_SHA256="invalida",
        HTTP_X_SHOPIFY_TOPIC="products/create",
    )

    assert resposta.status_code == 401
    assert not ExecucaoIntegracao.objects.exists()


@pytest.mark.django_db
def test_webhook_desabilitado_e_ignorado_sem_criar_tarefa(client, conta):
    """Desmarcar uma operacao deve interromper a entrada no limite HTTP."""
    configuracao = _configuracao(conta, habilitado=False)
    corpo = b'{"id": 123}'
    url = f"/integracoes/shopify/webhook/{configuracao.uuid}/produtos/"

    resposta = client.post(
        url,
        data=corpo,
        content_type="application/json",
        HTTP_X_SHOPIFY_HMAC_SHA256=_assinatura(corpo),
        HTTP_X_SHOPIFY_TOPIC="products/create",
    )

    assert resposta.status_code == 204
    assert not ExecucaoIntegracao.objects.exists()
