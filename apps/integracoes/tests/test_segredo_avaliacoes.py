"""Segredo das avaliacoes na tela da integracao Shopify."""

import pytest

from apps.integracoes.models import ConfiguracaoIntegracao
from apps.integracoes.tests.test_configuracao import URL, _dados

pytestmark = pytest.mark.django_db


def test_segredo_fica_criptografado_e_vazio_mantem_o_salvo(admin_logado):
    """Salvar a tela sem redigitar o segredo nao pode apagar o que o tema usa."""
    admin_logado.post(URL, _dados(segredo_avaliacoes="segredo-do-tema"))
    config = ConfiguracaoIntegracao.objects.get()
    assert config.segredo_avaliacoes == "segredo-do-tema"
    assert "segredo-do-tema" not in config.segredo_avaliacoes_criptografado

    admin_logado.post(URL, _dados(token_acesso="", segredo_app=""))
    assert ConfiguracaoIntegracao.objects.get().segredo_avaliacoes == "segredo-do-tema"


def test_endereco_para_o_tema_usa_a_url_publica_do_hub(admin_logado):
    """Com o admin aberto em localhost, o endereco do host apontaria para onde a loja nao chega."""
    admin_logado.post(URL, _dados())
    config = ConfiguracaoIntegracao.objects.get()
    pagina = admin_logado.get(URL).content.decode()
    assert f"https://hub.test/integracoes/shopify/avaliacoes/{config.pk}/" in pagina
