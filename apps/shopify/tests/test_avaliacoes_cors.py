"""Origem do tema na API de avaliacoes: so os dominios da conta da integracao."""

import pytest
from django.core.exceptions import ValidationError

from apps.integracoes.models import ConfiguracaoIntegracao

pytestmark = pytest.mark.django_db


@pytest.fixture
def config(conta):
    conta.dominio_avaliacoes = "minhaloja.com.br, www.minhaloja.com.br"
    conta.save()
    return ConfiguracaoIntegracao.objects.create(account=conta, dominio_loja="loja.myshopify.com")


def _preflight(client, config, origem):
    return client.options(
        f"/integracoes/shopify/avaliacoes/{config.pk}/",
        headers={"Origin": origem, "Access-Control-Request-Method": "POST"},
    )


@pytest.mark.parametrize("origem", ["https://minhaloja.com.br", "https://www.minhaloja.com.br"])
def test_cada_dominio_da_lista_pode_enviar_avaliacao(client, config, origem):
    """Loja com e sem www: com um dominio so, o outro endereco recebia 403."""
    resposta = _preflight(client, config, origem)

    assert resposta.status_code == 204
    assert resposta["Access-Control-Allow-Origin"] == origem


@pytest.mark.parametrize("origem", ["https://outraloja.com.br", "http://minhaloja.com.br",
                                    "https://minhaloja.com.br, www.minhaloja.com.br"])
def test_origem_fora_da_lista_continua_recusada(client, config, origem):
    """A lista nao pode virar coringa: o texto inteiro ou http:// nao passam."""
    assert _preflight(client, config, origem).status_code == 403


def test_conta_normaliza_a_lista_de_dominios(conta):
    conta.dominio_avaliacoes = " MinhaLoja.com.br ,www.minhaloja.com.br,, minhaloja.com.br "
    conta.full_clean()

    assert conta.dominio_avaliacoes == "minhaloja.com.br, www.minhaloja.com.br"


def test_conta_recusa_a_lista_com_um_dominio_invalido_e_diz_qual(conta):
    conta.dominio_avaliacoes = "minhaloja.com.br, https://www.minhaloja.com.br/loja"

    with pytest.raises(ValidationError, match="https://www.minhaloja.com.br/loja"):
        conta.full_clean()
