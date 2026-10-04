"""Cadastro do StarHub como calculadora de frete da loja (CarrierService)."""

from unittest.mock import Mock

import pytest

from apps.core.models import ExternalReference
from apps.integracoes import admin as admin_integracoes
from apps.integracoes.models import ExecucaoIntegracao
from apps.shopify import frete_cadastro
from apps.shopify.cliente import ShopifyErro
from apps.shopify.tests.test_webhooks import _configuracao

pytestmark = pytest.mark.django_db
GID = "gid://shopify/DeliveryCarrierService/9"


class LojaFalsa:
    def __init__(self, existentes=(), erros=()):
        self.chamadas, self.existentes, self.erros = [], list(existentes), list(erros)

    def graphql(self, query, variables=None):
        self.chamadas.append((query, variables))
        if "carrierServices(" in query:
            return {"carrierServices": {"nodes": self.existentes}}
        campo = "carrierServiceUpdate" if "Update" in query else "carrierServiceCreate"
        return {campo: {"userErrors": self.erros, "carrierService": {"id": GID}}}


@pytest.fixture
def configuracao(conta):
    configuracao = _configuracao(conta)
    configuracao.url_webhook = "https://hub.test/integracoes/shopify/webhook"
    configuracao.token_acesso = "shpat_teste"  # a tela exige token salvo
    configuracao.save()
    return configuracao


def _cadastrar(configuracao, loja):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(frete_cadastro, "ShopifyClient", lambda _config: loja)
        return frete_cadastro.cadastrar_frete(configuracao, lambda *_: None)


def test_cria_com_a_url_de_cotacao_e_guarda_o_id(configuracao):
    loja = LojaFalsa()
    _cadastrar(configuracao, loja)
    entrada = loja.chamadas[-1][1]["input"]
    assert entrada["callbackUrl"] == (
        f"https://hub.test/integracoes/shopify/frete/{configuracao.uuid}/")
    assert entrada["name"] == frete_cadastro.NOME and entrada["active"] is True
    assert ExternalReference.objects.get(entity_type="carrier_service").external_id == GID


def test_cadastrar_de_novo_atualiza_o_mesmo_e_nao_cria_outro(configuracao):
    """Dois cadastros mostrariam as opcoes do hub em dobro no checkout."""
    _cadastrar(configuracao, LojaFalsa())
    loja = LojaFalsa()
    mensagem = _cadastrar(configuracao, loja)
    assert "carrierServiceUpdate" in loja.chamadas[-1][0] and "atualizado" in mensagem
    assert loja.chamadas[-1][1]["input"]["id"] == GID
    assert ExternalReference.objects.filter(entity_type="carrier_service").count() == 1


def test_sem_vinculo_acha_o_cadastro_da_loja_pelo_nome(configuracao):
    loja = LojaFalsa(existentes=[{"id": GID, "name": frete_cadastro.NOME}])
    _cadastrar(configuracao, loja)
    assert "carrierServiceUpdate" in loja.chamadas[-1][0]


def test_sem_https_ou_com_erro_da_loja_explica_o_que_fazer(configuracao):
    configuracao.url_webhook = "http://localhost:8000/integracoes/shopify/webhook"
    with pytest.raises(ValueError, match="https"):
        _cadastrar(configuracao, LojaFalsa())
    configuracao.url_webhook = "https://hub.test/x"
    with pytest.raises(ShopifyErro, match="third-party"):
        _cadastrar(configuracao, LojaFalsa(erros=[{"message": "third-party calculated "
                                                              "shipping rates not enabled"}]))


def test_botao_da_tela_coloca_o_cadastro_na_fila(admin_logado, configuracao, monkeypatch):
    tarefa = Mock()
    tarefa.delay.return_value = Mock(id="celery-1")
    monkeypatch.setitem(admin_integracoes.ACOES, "frete",
                        (ExecucaoIntegracao.Tipo.FRETE_CHECKOUT, tarefa))
    pagina = "/admin/integracoes/configuracaointegracao/shopify/"
    assert "Cadastrar frete no checkout" in admin_logado.get(pagina).content.decode()
    admin_logado.post(pagina, {"acao": "frete", "dominio_loja": "loja.myshopify.com",
                               "url_webhook": configuracao.url_webhook, "active": "on"})
    execucao = ExecucaoIntegracao.objects.get(tipo=ExecucaoIntegracao.Tipo.FRETE_CHECKOUT)
    tarefa.delay.assert_called_once_with(str(execucao.pk))
