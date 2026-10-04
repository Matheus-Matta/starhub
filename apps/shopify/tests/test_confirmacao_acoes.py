"""Acao que altera a loja real pede confirmacao antes (dialogo do confirmar.js)."""

import re

import pytest

from apps.integracoes.models import ConfiguracaoIntegracao
from apps.shopify.tests.test_frete_cadastro import configuracao  # noqa: F401 (fixture)

pytestmark = pytest.mark.django_db
PAGINA = "/admin/integracoes/configuracaointegracao/shopify/"
ESCREVEM_NA_LOJA = {"webhooks", "frete", "frete_desativar", "frete_ativar"}


def _botoes(html):
    """{value do botao acao: tem data-confirmar?}"""
    return {m.group(2): "data-confirmar=" in m.group(1) + m.group(3)
            for m in re.finditer(r'<button([^>]*?)name="acao" value="([^"]+)"([^>]*)>', html)}


def test_toda_acao_que_escreve_na_loja_pede_confirmacao(admin_logado, configuracao):  # noqa: F811
    """Um clique por engano cadastrou o frete na loja real: escrita la so confirmada."""
    botoes = _botoes(admin_logado.get(PAGINA).content.decode())
    ConfiguracaoIntegracao.objects.filter(pk=configuracao.pk).update(frete_ativo=False)
    botoes |= _botoes(admin_logado.get(PAGINA).content.decode())
    assert ESCREVEM_NA_LOJA <= set(botoes)
    assert all(botoes[acao] for acao in ESCREVEM_NA_LOJA), botoes
    assert botoes["verificar_frete"] is False  # so le a loja: sem dialogo
    assert botoes["salvar"] is False


def test_o_dialogo_e_o_script_estao_em_toda_pagina_do_admin(admin_logado):
    html = admin_logado.get("/admin/").content.decode()
    assert 'id="sh-confirmar"' in html and "starhub/js/confirmar.js" in html
