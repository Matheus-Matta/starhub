"""Checklist do frete no checkout: verificacao na loja (tarefa) e a tela da Shopify."""

from decimal import Decimal
from unittest.mock import Mock

import pytest

from apps.core.models import ExternalReference
from apps.integracoes import admin as admin_integracoes
from apps.integracoes.models import ExecucaoIntegracao
from apps.logistica.models import TabelaFrete
from apps.loja.services.variantes import criar_produto
from apps.shopify import frete_diagnostico
from apps.shopify.cliente import ShopifyErro
from apps.shopify.frete_checklist import checklist
from apps.shopify.tests.test_frete_cadastro import configuracao  # noqa: F401 (fixture)

pytestmark = pytest.mark.django_db
GID = "gid://shopify/DeliveryCarrierService/9"


def _respostas(url, zonas=True, escopos=("read_shipping", "write_shipping"), plano_falha=False):
    metodo = {"name": "StarHub", "active": True,
              "rateProvider": {"carrierService": {"id": GID if zonas else "outro"}}}
    return {
        "currentAppInstallation": {"accessScopes": [{"handle": e} for e in escopos]},
        "shop": ShopifyErro("Field 'publicDisplayName' doesn't exist") if plano_falha else
        {"plan": {"publicDisplayName": "Basic", "partnerDevelopment": False,
                  "shopifyPlus": False}},
        "carrierServices": {"nodes": [{"id": GID, "name": "StarHub Frete", "callbackUrl": url,
                                       "active": True}]},
        "locations": {"nodes": [{"name": "Deposito", "isActive": True,
                                 "address": {"zip": "01001-000", "city": "Sao Paulo"}}]},
        "deliveryProfiles": {"nodes": [{"name": "Geral", "profileLocationGroups": [
            {"locationGroupZones": {"nodes": [{"zone": {"name": "Brasil"},
                                               "methodDefinitions": {"nodes": [metodo]}}]}}]}]},
    }


class LojaFalsa:
    def __init__(self, respostas):
        self.respostas = respostas

    def graphql(self, query, variables=None):
        for raiz, resposta in self.respostas.items():
            if f"{raiz} " in query or f"{raiz}(" in query:
                if isinstance(resposta, Exception):
                    raise resposta
                return {raiz: resposta}
        raise ShopifyErro("consulta nao prevista")


def _verificar(loja, **kwargs):
    url = frete_diagnostico.url_de_cotacao(loja)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(frete_diagnostico, "ShopifyClient",
                   lambda _c: LojaFalsa(_respostas(url, **kwargs)))
        frete_diagnostico.verificar(loja, lambda *_: None)
    return {i["titulo"]: i for i in checklist(loja)["itens"]}


def test_loja_toda_certa_fica_verde(configuracao):  # noqa: F811
    TabelaFrete.objects.create(nome="SP", tipo="faixa_cep", no_checkout=True)
    itens = _verificar(configuracao)
    for titulo in ("Escopos read_shipping e write_shipping", "Frete do StarHub cadastrado na loja",
                   "Ligado a zona de envio", "CEP dos locais de estoque",
                   "Tabelas de frete no checkout", "Plano libera frete de terceiros"):
        assert itens[titulo]["estado"] == "ok", titulo
    assert itens["Ligado a zona de envio"]["detalhe"] == "Geral / Brasil"
    assert "01001-000" in itens["CEP dos locais de estoque"]["detalhe"]
    assert itens["Embalagem padrao"]["estado"] == "manual"


def test_o_que_falta_aparece_com_o_caminho_para_resolver(configuracao):  # noqa: F811
    itens = _verificar(configuracao, zonas=False, escopos=("read_shipping",))
    assert itens["Escopos read_shipping e write_shipping"]["estado"] == "falta"
    assert "write_shipping" in itens["Escopos read_shipping e write_shipping"]["detalhe"]
    assert itens["Ligado a zona de envio"]["estado"] == "falta"
    assert "Usar transportadora ou app" in itens["Ligado a zona de envio"]["como"]
    assert itens["Tabelas de frete no checkout"]["estado"] == "falta"


def test_consulta_que_falha_nao_derruba_as_outras(configuracao):  # noqa: F811
    """Campo que muda na API da Shopify vira "nao deu para verificar", nao erro na tarefa."""
    itens = _verificar(configuracao, plano_falha=True)
    assert itens["Frete do StarHub cadastrado na loja"]["estado"] == "ok"
    vinculo = ExternalReference.objects.get(entity_type="frete_checkout")
    assert "publicDisplayName" in vinculo.metadata["plano"]["erro"]


def test_cadastro_recusado_por_plano_mostra_a_solucao(configuracao):  # noqa: F811
    ExecucaoIntegracao.objects.create(
        configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.FRETE_CHECKOUT, status="failed",
        mensagem="Shopify respondeu HTTP 403: Forbidden")
    plano = {i["titulo"]: i for i in checklist(configuracao)["itens"]}[
        "Plano libera frete de terceiros"]
    assert plano["estado"] == "falta" and "Third-party" in plano["como"]


def test_sem_verificacao_fica_pendente_e_peso_vem_do_hub(configuracao):  # noqa: F811
    produto = criar_produto("Mesa", sku="M-1", price=Decimal("10"))
    ExternalReference.objects.create(platform="shopify", entity_type="variantes",
                                     object_id=str(produto.variante_padrao.pk),
                                     external_id="gid://shopify/ProductVariant/1")
    itens = {i["titulo"]: i for i in checklist(configuracao)["itens"]}
    assert itens["Frete do StarHub cadastrado na loja"]["estado"] == "pendente"
    assert itens["Peso nos produtos"]["estado"] == "aviso"
    assert "1 variante(s)" in itens["Peso nos produtos"]["detalhe"]


def test_tela_mostra_o_checklist_e_o_botao_verificar_vai_para_a_fila(
        admin_logado, configuracao, monkeypatch):  # noqa: F811
    tarefa = Mock()
    tarefa.delay.return_value = Mock(id="c1")
    monkeypatch.setitem(admin_integracoes.ACOES, "verificar_frete",
                        (ExecucaoIntegracao.Tipo.VERIFICAR_FRETE, tarefa))
    pagina = "/admin/integracoes/configuracaointegracao/shopify/"
    html = admin_logado.get(pagina).content.decode()
    assert "Frete no checkout" in html and "Verificar configuracao" in html
    admin_logado.post(pagina, {"acao": "verificar_frete", "dominio_loja": "loja.myshopify.com",
                               "url_webhook": configuracao.url_webhook, "active": "on"})
    execucao = ExecucaoIntegracao.objects.get(tipo=ExecucaoIntegracao.Tipo.VERIFICAR_FRETE)
    tarefa.delay.assert_called_once_with(str(execucao.pk))


def test_plano_advanced_ja_libera_e_origem_diferente_do_local_avisa(configuracao):  # noqa: F811
    """O CEP de origem da tabela e de onde o km e medido: longe do deposito, frete errado."""
    TabelaFrete.objects.create(nome="Km SP", tipo="distancia", cep_origem="01001000",
                               preco_por_km=Decimal("1"), no_checkout=True)
    url = frete_diagnostico.url_de_cotacao(configuracao)
    respostas = _respostas(url)
    respostas["shop"] = {"plan": {"publicDisplayName": "Advanced", "shopifyPlus": False,
                                  "partnerDevelopment": False}}
    respostas["carrierServices"] = {"nodes": []}
    respostas["locations"] = {"nodes": [{"name": "Deposito Niteroi", "isActive": True,
                                         "address": {"zip": "24325-300", "city": "Niteroi"}}]}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(frete_diagnostico, "ShopifyClient", lambda _c: LojaFalsa(respostas))
        frete_diagnostico.verificar(configuracao, lambda *_: None)
    itens = {i["titulo"]: i for i in checklist(configuracao)["itens"]}
    assert itens["Plano libera frete de terceiros"]["estado"] == "ok"
    origem = itens["Origem das tabelas por distancia"]
    assert origem["estado"] == "aviso" and "Km SP" in origem["detalhe"]
