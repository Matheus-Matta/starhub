"""Botao "JSON" do pedido: o que o ERP recebe, os vinculos e os webhooks recebidos."""

import pytest

from apps.core.models import ExternalReference, Origin
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.loja.models import Pedido


def _webhook(configuracao, dados, requisicao=None):
    parametros = {"reenvio": {"recurso": "pedidos", "operacao": "update", "dados": dados}}
    if requisicao is not None:
        parametros["requisicao"] = requisicao
    return ExecucaoIntegracao.objects.create(
        configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.RECEBER,
        etapa="Webhook orders/updated", parametros=parametros)


@pytest.fixture
def pedido(db):
    pedido = Pedido.objects.create(number="SH-0001", external_number="1001",
                                   origin=Origin.SHOPIFY)
    ExternalReference.objects.create(platform=Origin.SHOPIFY, entity_type="pedidos",
                                     external_id="gid://shopify/Order/555",
                                     object_id=str(pedido.pk), metadata={"nome": "#1001"})
    return pedido


@pytest.mark.django_db
def test_pedido_mostra_o_json_do_erp_o_vinculo_e_so_os_webhooks_dele(admin_logado, pedido):
    """Sem esta tela, conferir o que chegou da loja exigia achar a tarefa certa entre todas."""
    shopify = ConfiguracaoIntegracao.objects.create(nome="Shopify",
                                                    dominio_loja="loja.myshopify.com")
    _webhook(shopify, {"id": 555, "admin_graphql_api_id": "gid://shopify/Order/555",
                       "note": "corpo-deste-pedido"})
    _webhook(shopify, {"id": 999, "note": "corpo-de-outro-pedido"})

    html = admin_logado.get(f"/admin/loja/pedido/{pedido.pk}/json/").content.decode()

    assert "&quot;order_key&quot;" in html  # JSON da API Woo, igual ao GET do ERP
    assert "gid://shopify/Order/555" in html and "#1001" in html
    assert "corpo-deste-pedido" in html
    assert "corpo-de-outro-pedido" not in html


@pytest.mark.django_db
def test_webhook_do_suri_mostra_o_corpo_inteiro_e_nao_so_o_id(admin_logado):
    """O reenvio do Suri guarda so {"id"}: o corpo recebido fica na requisicao."""
    pedido = Pedido.objects.create(number="SH-0002", origin=Origin.SURI)
    ExternalReference.objects.create(platform=Origin.SURI, entity_type="pedidos",
                                     external_id="77", object_id=str(pedido.pk))
    suri = ConfiguracaoIntegracao.objects.create(
        nome="Suri", plataforma=ConfiguracaoIntegracao.Plataforma.SURI)
    _webhook(suri, {"id": "77"}, requisicao={"metodo": "POST", "caminho": "/x/",
                                             "corpo": {"orderId": "77", "total": "corpo-suri"}})

    html = admin_logado.get(f"/admin/loja/pedido/{pedido.pk}/json/").content.decode()

    assert "corpo-suri" in html


@pytest.mark.django_db
def test_tela_do_pedido_tem_o_botao_json(admin_logado, pedido):
    html = admin_logado.get(f"/admin/loja/pedido/{pedido.pk}/change/").content.decode()
    assert f"/admin/loja/pedido/{pedido.pk}/json/" in html
