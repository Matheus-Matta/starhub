"""Tarefa que busca o CPF dos pedidos antigos do Shopify que vieram sem documento."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.loja.models import Cliente, Pedido
from apps.loja.services.variantes import criar_produto
from apps.shopify import pedidos_documento_lote as lote
from apps.shopify.cliente import ShopifyClient, ShopifyErro
from apps.shopify.contexto import coletando_avisos, usando_configuracao
from apps.shopify.pedidos import importar_pedido
from apps.shopify.tests.pedido_exemplo import pedido_shopify, produto_shopify_falso  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("produto_shopify_falso")]
GID = "gid://shopify/Order/123456789"
CPF = "39053344705"


def _no(gid=GID, valor=CPF):
    return {"id": gid, "name": "#1001", "localizationExtensions": {"nodes": [
        {"purpose": "TAX", "countryCode": "BR", "title": "CPF/CNPJ", "value": valor}]}}


@pytest.fixture
def loja(monkeypatch):
    criar_produto("Poltrona Exemplo", sku="POLTRONA-001", price=Decimal("1499.90"))
    # Pedido "antigo": importado antes da busca do documento, sem CPF.
    monkeypatch.setattr("apps.shopify.pedidos.completar_documento", lambda dados: dados)
    importar_pedido(pedido_shopify(note_attributes=[]))
    monkeypatch.undo()
    return ConfiguracaoIntegracao.objects.create(nome="Shopify",
                                                 dominio_loja="loja.myshopify.com")


def _shopify(monkeypatch, *respostas):
    """Cada chamada devolve a proxima resposta (ou levanta, se for excecao)."""
    chamadas, fila = [], list(respostas)

    def graphql(self, query, variables=None):
        chamadas.append((self.endpoint, variables))
        resposta = fila.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return {"nodes": resposta}

    monkeypatch.setattr(ShopifyClient, "graphql", graphql)
    monkeypatch.setattr(lote.time, "sleep", lambda _segundos: None)
    return chamadas


def _rodar(loja, pedidos=None):
    with usando_configuracao(loja), coletando_avisos() as avisos:
        mensagem = lote.preencher_documentos(loja, lambda *_: None, pedidos)
    return mensagem, avisos


def test_pedido_antigo_sem_cpf_ganha_o_cpf_no_billing_e_no_cliente(loja, monkeypatch):
    """Pedidos importados antes da busca do documento chegavam ao ERP sem CPF."""
    chamadas = _shopify(monkeypatch, [_no()])
    mensagem, avisos = _rodar(loja)
    pedido = Pedido.objects.get()
    assert pedido.endereco_cobranca.document == CPF
    assert pedido.endereco_cobranca.metadata["persontype"] == "1"
    assert pedido.cliente.cpf == CPF
    assert "1 preenchido(s)" in mensagem and not avisos
    assert chamadas == [("https://loja.myshopify.com/admin/api/2024-01/graphql.json",
                         {"ids": [GID]})]


def test_pedido_que_ja_tem_cpf_nao_e_consultado(loja, monkeypatch):
    _shopify(monkeypatch, [_no()])
    _rodar(loja)
    chamadas = _shopify(monkeypatch)
    mensagem, _avisos = _rodar(loja)
    assert chamadas == [] and mensagem.startswith("0 pedido(s)")


def test_pedido_sem_cpf_no_checkout_fica_como_esta(loja, monkeypatch):
    _shopify(monkeypatch, [{"id": GID, "localizationExtensions": {"nodes": []}}])
    mensagem, _avisos = _rodar(loja)
    assert Pedido.objects.get().endereco_cobranca.document == ""
    assert "1 sem CPF no checkout" in mensagem


def test_limite_de_taxa_do_shopify_espera_e_tenta_de_novo(loja, monkeypatch):
    """Sem tentar de novo, centenas de pedidos parariam no primeiro THROTTLED."""
    chamadas = _shopify(monkeypatch, ShopifyErro("Throttled"), [_no()])
    _rodar(loja)
    assert len(chamadas) == 2
    assert Pedido.objects.get().cliente.cpf == CPF


def test_cpf_do_cliente_ja_preenchido_nao_e_trocado(loja, monkeypatch):
    Cliente.objects.filter(pk=Pedido.objects.get().cliente_id).update(cpf="52998224725")
    _shopify(monkeypatch, [_no()])
    _rodar(loja)
    pedido = Pedido.objects.get()
    assert (pedido.endereco_cobranca.document, pedido.cliente.cpf) == (CPF, "52998224725")


def test_acao_da_lista_cria_a_tarefa_so_com_os_pedidos_sem_cpf(admin_logado, loja):
    """A consulta roda no worker; a acao so enfileira os pedidos que precisam."""
    pedido = Pedido.objects.get()
    resposta = admin_logado.post(reverse("admin:loja_pedido_changelist"), {
        "action": "buscar_cpf_no_shopify", "_selected_action": [pedido.pk]})
    execucao = ExecucaoIntegracao.objects.get(tipo=ExecucaoIntegracao.Tipo.CPF_PEDIDOS)
    assert execucao.parametros == {"pedidos": [pedido.pk]}
    assert resposta.url == reverse("admin:integracoes_execucaointegracao_change",
                                   args=[execucao.pk])
