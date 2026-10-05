"""Tela de configuracao do Suri Shop no admin."""

import pytest
from django.urls import reverse

from apps.integracoes.models import ConfiguracaoIntegracao

pytestmark = pytest.mark.django_db
URL = "admin:integracoes_configuracaointegracao_suri"


def test_salvar_cria_a_configuracao_do_suri_sem_o_api_no_fim(admin_logado):
    resposta = admin_logado.post(reverse(URL), {
        "dominio_loja": "https://cbteste.azurewebsites.net/api", "token_acesso": "tk",
        "url_webhook": "https://hub.test/integracoes/suri/webhook", "active": "on",
        "receber__pedidos__create": "on", "acao": "salvar"})

    assert resposta.status_code == 302
    cfg = ConfiguracaoIntegracao.objects.get()
    assert (cfg.plataforma, cfg.nome, cfg.dominio_loja) == (
        "suri", "Suri Shop", "https://cbteste.azurewebsites.net")
    assert cfg.token_acesso == "tk" and cfg.habilitado("receber", "pedidos", "create")


def test_tela_abre_sem_segredo_e_com_o_item_no_menu(admin_logado):
    resposta = admin_logado.get(reverse(URL))

    html = resposta.content.decode()
    assert resposta.status_code == 200 and "Integracao Suri Shop" in html
    assert 'name="segredo_app"' not in html and "Endpoint do chatbot" in html
    assert reverse(URL) in html


def test_menu_e_badge_de_origem_usam_o_logo_do_suri(admin_logado):
    """Sem SVG publico do Suri, o menu caia no icone de pasta."""
    from apps.core.admin_utils import badge_origem

    html = admin_logado.get(reverse(URL)).content.decode()

    assert 'class="sh-marca" src="/static/starhub/img/marcas/suri.png"' in html
    assert "marcas/suri.png" in badge_origem("suri", "Suri Shop")


def test_ligar_frete_do_suri_so_marca_no_hub(admin_logado):
    from apps.suri.frete import frete_ligado

    admin_logado.post(reverse(URL), {"dominio_loja": "https://cb.azurewebsites.net",
                                     "token_acesso": "tk", "acao": "frete_ligar"})

    assert frete_ligado(ConfiguracaoIntegracao.objects.get())
    assert "Frete ligado" in admin_logado.get(reverse(URL)).content.decode()
