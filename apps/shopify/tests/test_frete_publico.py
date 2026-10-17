"""Consulta de frete usada pelo calculador do tema da loja."""

from decimal import Decimal

import pytest

from apps.integracoes.models import ConfiguracaoIntegracao
from apps.logistica.models import FaixaCep, TabelaFrete

pytestmark = pytest.mark.django_db


@pytest.fixture
def configuracao(conta):
    conta.dominio_avaliacoes = "www.loja.com.br, loja.com.br"
    conta.save(update_fields=["dominio_avaliacoes"])
    config = ConfiguracaoIntegracao.objects.create(
        account=conta, plataforma="shopify", dominio_loja="loja.myshopify.com",
    )
    tabela = TabelaFrete.objects.create(
        nome="Entrega propria", tipo="faixa_cep", prazo_dias=3, no_checkout=True,
    )
    FaixaCep.objects.create(
        tabela=tabela, cep_inicial="20000000", cep_final="28999999",
        valor=Decimal("39.99"),
    )
    return config


def _url(configuracao):
    return f"/integracoes/shopify/frete-publico/{configuracao.uuid}/"


@pytest.mark.parametrize("origem", [
    "https://loja.myshopify.com", "https://www.loja.com.br", "https://loja.com.br",
])
def test_dominio_cadastrado_pode_consultar_frete(client, configuracao, origem):
    resposta = client.get(_url(configuracao), {"cep": "24400-000"},
                          headers={"Origin": origem})

    assert resposta.status_code == 200
    assert resposta["Access-Control-Allow-Origin"] == origem
    assert "Origin" in resposta["Vary"]
    opcao = resposta.json()["rates"][0]
    assert (opcao["service_name"], opcao["total_price"]) == ("Entrega propria", "3999")


@pytest.mark.parametrize("origem", [None, "https://outra-loja.com.br", "http://loja.com.br"])
def test_consulta_recusa_navegador_fora_dos_dominios(client, configuracao, origem):
    headers = {"Origin": origem} if origem else {}

    resposta = client.get(_url(configuracao), {"cep": "24400-000"}, headers=headers)

    assert resposta.status_code == 403
    assert "Access-Control-Allow-Origin" not in resposta


def test_preflight_libera_get_somente_para_origem_cadastrada(client, configuracao):
    resposta = client.options(
        _url(configuracao),
        headers={"Origin": "https://loja.com.br", "Access-Control-Request-Method": "GET"},
    )

    assert resposta.status_code == 204
    assert resposta["Access-Control-Allow-Origin"] == "https://loja.com.br"
    assert resposta["Access-Control-Allow-Methods"] == "GET"


def test_consulta_respeita_opcao_de_ocultar_prazo(client, configuracao):
    configuracao.exibir_prazo_frete = False
    configuracao.save(update_fields=["exibir_prazo_frete"])

    resposta = client.get(_url(configuracao), {"cep": "24400-000"},
                          headers={"Origin": "https://loja.com.br"})
    opcao = resposta.json()["rates"][0]

    assert {"description", "min_delivery_date", "max_delivery_date"}.isdisjoint(opcao)
