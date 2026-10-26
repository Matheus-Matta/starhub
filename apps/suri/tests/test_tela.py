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


def test_tela_mostra_os_tres_campos_para_configurar_a_logistica_no_suri(admin_logado):
    admin_logado.post(reverse(URL), {
        "dominio_loja": "https://cb.azurewebsites.net", "token_acesso": "tk",
        "url_webhook": "https://hub.test/integracoes/suri/webhook", "active": "on",
        "acao": "salvar"})
    cfg = ConfiguracaoIntegracao.objects.get()

    html = admin_logado.get(reverse(URL)).content.decode()

    assert f"https://hub.test/integracoes/suri/logistica/{cfg.uuid}/" in html
    assert "API URL" in html and "Header Key" in html and "Header Value" in html
    assert "Authorization" in html and "Bearer SEU_TOKEN_DA_API_DO_SURI" in html
    assert "Bearer tk" not in html, "a tela nao deve revelar o token salvo"


def test_servicos_ligam_envio_e_recebimento_na_tela_do_suri(admin_logado):
    """Sem o campo na tela o operador nao tinha como ligar os servicos no Suri."""
    html = admin_logado.get(reverse(URL)).content.decode()
    assert 'name="enviar_servicos"' in html and 'name="receber_servicos"' in html

    admin_logado.post(reverse(URL), {
        "dominio_loja": "https://cb.azurewebsites.net", "token_acesso": "tk",
        "enviar_servicos": "on", "receber_servicos": "on", "acao": "salvar"})

    cfg = ConfiguracaoIntegracao.objects.get()
    assert cfg.enviar_servicos and cfg.receber_servicos


def test_so_a_tela_da_shopify_oferece_servicos_no_tema(admin_logado):
    """O bloco da pagina do produto e do tema Shopify; no Suri e no Woo o campo nao existe."""
    shopify = admin_logado.get(
        reverse("admin:integracoes_configuracaointegracao_shopify")).content.decode()
    suri = admin_logado.get(reverse(URL)).content.decode()
    woo = admin_logado.get(
        reverse("admin:integracoes_configuracaointegracao_woocommerce")).content.decode()

    assert 'name="servicos_no_tema"' in shopify and 'name="servicos_no_tema"' not in suri
    assert 'name="enviar_servicos"' not in woo
