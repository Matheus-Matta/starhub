"""Tela de configuracao do WooCommerce no admin e o item dela no menu."""

import pytest
from django.urls import reverse

from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao

pytestmark = pytest.mark.django_db
URL = "admin:integracoes_configuracaointegracao_woocommerce"


def test_salvar_cria_a_configuracao_do_woocommerce_com_o_nome_dela(admin_logado):
    """A tela copiada do Shopify gravava a loja Woo com o nome "Shopify"."""
    resposta = admin_logado.post(reverse(URL), {
        "dominio_loja": "https://loja.test/", "token_acesso": "ck_1", "segredo_app": "cs_1",
        "url_webhook": "https://hub.test/integracoes/woocommerce/webhook", "active": "on",
        "receber__produtos__get": "on", "acao": "salvar"})

    assert resposta.status_code == 302
    cfg = ConfiguracaoIntegracao.objects.get()
    assert (cfg.plataforma, cfg.nome, cfg.dominio_loja) == (
        "woocommerce", "WooCommerce", "https://loja.test")
    assert cfg.token_acesso == "ck_1" and cfg.habilitado("receber", "produtos", "get")


def test_dominio_sem_https_e_recusado(admin_logado):
    resposta = admin_logado.post(reverse(URL), {
        "dominio_loja": "loja.test", "token_acesso": "ck_1", "segredo_app": "cs_1",
        "acao": "salvar"})

    assert resposta.status_code == 200 and not ConfiguracaoIntegracao.objects.exists()
    assert "https://sualoja.com.br" in resposta.content.decode()


def test_cadastrar_webhooks_vai_para_a_tarefa_do_woocommerce(admin_logado, monkeypatch):
    enfileiradas = []
    monkeypatch.setattr("apps.integracoes.admin.enfileirar",
                        lambda tarefa, *args: enfileiradas.append(tarefa.name) or
                        type("R", (), {"id": "x"})())
    admin_logado.post(reverse(URL), {
        "dominio_loja": "https://loja.test", "token_acesso": "ck_1", "segredo_app": "cs_1",
        "url_webhook": "https://hub.test/w", "acao": "webhooks"})

    assert enfileiradas == ["apps.woocommerce.tasks.cadastrar_webhooks_woocommerce"]
    assert ExecucaoIntegracao.objects.get().tipo == ExecucaoIntegracao.Tipo.WEBHOOKS


def test_menu_mostra_o_woocommerce_com_o_logo_e_a_tela_abre(admin_logado):
    resposta = admin_logado.get(reverse(URL))

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Integracao WooCommerce" in html and "ck_..." in html
    assert "Frete no checkout" not in html and "segredo_avaliacoes" not in html
    assert reverse(URL) in html


def test_ligar_e_desligar_frete_vao_para_a_tarefa_de_zonas(admin_logado, monkeypatch):
    monkeypatch.setattr("apps.woocommerce.frete_sinais.enfileirar",
                        lambda tarefa, *args: type("R", (), {"id": "x"}))
    dados = {"dominio_loja": "https://loja.test", "token_acesso": "ck_1", "segredo_app": "cs_1"}
    admin_logado.post(reverse(URL), {**dados, "acao": "frete_ligar"})
    admin_logado.post(reverse(URL), {**dados, "acao": "frete_desligar"})

    remover = [e.parametros["remover"] for e in ExecucaoIntegracao.objects.order_by("pk")]
    assert remover == [False, True]
    assert "Frete do hub" in admin_logado.get(reverse(URL)).content.decode()


def test_so_o_superusuario_ve_e_liga_o_encaminhamento(admin_logado, client, conta):
    from django.contrib.auth.models import Permission

    from apps.core.models import User

    dados = {"dominio_loja": "https://loja.test", "token_acesso": "ck_1", "segredo_app": "cs_1",
             "acao": "salvar"}
    assert "Modo dos pedidos" in admin_logado.get(reverse(URL)).content.decode()
    admin_logado.post(reverse(URL), {**dados, "encaminhar_pedidos": "on"})
    assert ConfiguracaoIntegracao.objects.get().encaminhar_pedidos is True

    operador = User.objects.create_user("operador", "op@x.test", "senha-forte-123",
                                        account=conta, is_staff=True)
    operador.user_permissions.add(*Permission.objects.filter(
        codename__in=["view_configuracaointegracao", "change_configuracaointegracao"]))
    client.force_login(operador)
    tela = client.get(reverse(URL)).content.decode()
    client.post(reverse(URL), {**dados, "encaminhar_pedidos": ""})

    assert "Modo dos pedidos" not in tela
    assert ConfiguracaoIntegracao.objects.get().encaminhar_pedidos is True, \
        "operador sem superusuario nao desliga mandando o campo vazio"
