import pytest
from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction

from apps.core.models import User
from apps.integracoes.models import ConfiguracaoIntegracao

URL = "/admin/integracoes/configuracaointegracao/shopify/"
LISTA_URL = "/admin/integracoes/configuracaointegracao/"


def _dados(**extras):
    return {
        "nome": "Shopify principal",
        "dominio_loja": "minha-loja.myshopify.com",
        "versao_api": "2026-07",
        "token_acesso": "shpat_token-novo",
        "segredo_app": "segredo-novo",
        "url_webhook": "https://hub.test/integracoes/shopify/webhook/",
        "active": "on",
        "receber__produtos__get": "on",
        "receber__pedidos__create": "on",
        "enviar__estoque__update": "on",
        **extras,
    }


@pytest.mark.django_db
def test_entrada_da_sidebar_redireciona_para_pagina_shopify(admin_logado):
    """A URL padrao do ModelAdmin precisa resolver a pagina singleton sem erro 500."""
    resposta = admin_logado.get(LISTA_URL)

    assert resposta.status_code == 302
    assert resposta.url == URL


@pytest.mark.django_db
def test_existe_uma_configuracao_shopify_por_conta():
    """Duas telas concorrentes nao podem criar duas integracoes Shopify na mesma conta."""
    ConfiguracaoIntegracao.objects.create(nome="A", plataforma="shopify")

    with pytest.raises(IntegrityError), transaction.atomic():
        ConfiguracaoIntegracao.objects.create(nome="B", plataforma="shopify")


@pytest.mark.django_db
def test_token_e_segredo_nao_ficam_legiveis_no_banco():
    """Credencial da loja nunca pode ser persistida como texto puro ou reaparecer no form."""
    configuracao = ConfiguracaoIntegracao.objects.create(nome="Loja", plataforma="shopify")
    configuracao.token_acesso = "shpat_super-secreto"
    configuracao.segredo_app = "segredo-super-secreto"
    configuracao.save()

    configuracao.refresh_from_db()
    assert "shpat_super-secreto" not in configuracao.token_criptografado
    assert "segredo-super-secreto" not in configuracao.segredo_criptografado
    assert configuracao.token_acesso == "shpat_super-secreto"
    assert configuracao.segredo_app == "segredo-super-secreto"


@pytest.mark.django_db
def test_credenciais_salvas_nao_reaparecem_na_pagina(admin_logado):
    """A pagina avisa que ha credenciais sem devolver os valores ao navegador."""
    configuracao = ConfiguracaoIntegracao.objects.create(nome="Loja", plataforma="shopify")
    configuracao.token_acesso = "shpat_nao-exibir"
    configuracao.segredo_app = "segredo-nao-exibir"
    configuracao.save()

    html = admin_logado.get(URL).content.decode()

    assert "shpat_nao-exibir" not in html
    assert "segredo-nao-exibir" not in html
    assert "Token de acesso já configurado" in html
    assert "Segredo do app já configurado" in html


@pytest.mark.django_db
def test_pagina_shopify_exibe_configuracao_e_matriz_amigavel(admin_logado):
    """A integracao deve ser uma pagina unica, nao uma lista de politicas abstratas."""
    resposta = admin_logado.get(URL)
    html = resposta.content.decode()

    assert resposta.status_code == 200
    for texto in ("Shopify", "Produtos", "Categorias", "Clientes", "Pedidos", "Cupons",
                  "Estoque", "Buscar", "Criar", "Atualizar", "Excluir", "Receber", "Enviar"):
        assert texto in html
    assert "Cadastrar webhooks" in html
    assert "Sincronizar loja" in html
    assert 'name="nome"' not in html
    assert 'name="versao_api"' not in html
    assert 'name="client_id"' not in html


@pytest.mark.django_db
def test_url_do_webhook_vem_do_endereco_aberto_no_navegador(admin_logado):
    """Loja nova deve receber protocolo e dominio atuais sem digitacao manual."""
    html = admin_logado.get(URL).content.decode()

    assert 'value="http://testserver/integracoes/shopify/webhook"' in html


@pytest.mark.django_db
def test_campos_da_integracao_exibem_exemplos_de_preenchimento(admin_logado):
    """Credenciais tecnicas precisam indicar o formato esperado antes da digitacao."""
    html = admin_logado.get(URL).content.decode()

    for exemplo in (
        "sua-loja.myshopify.com",
        "shpat_...",
        "Client secret usado para assinar webhooks",
        "https://seu-dominio.com/integracoes/shopify/webhook",
    ):
        assert f'placeholder="{exemplo}"' in html
    assert "Token de acesso já configurado" not in html
    assert "Segredo do app já configurado" not in html


@pytest.mark.django_db
def test_matriz_tem_colunas_estaveis_e_acoes_de_marcacao(admin_logado):
    """Receber e Enviar devem compartilhar colunas e permitir selecao em lote."""
    html = admin_logado.get(URL).content.decode()

    assert html.count('data-direcao="receber"') == 7
    assert html.count('data-direcao="enviar"') == 7
    assert html.count('<td class="integracao-direcao"') == 14
    assert html.count('class="integracao-operacao"') == 56
    for acao in ("todos", "receber", "enviar", "nenhum"):
        assert f'data-integracao-marcar="{acao}"' in html
    assert "starhub/js/integracao-matriz.js" in html


@pytest.mark.django_db
def test_menu_troca_politicas_por_configuracao_e_tarefas(admin_logado):
    """O usuario nao deve mais navegar por politica/canal/estado de publicacao."""
    html = admin_logado.get("/admin/").content.decode()

    secoes = {app["app_label"]: [m["name"] for m in app["models"]]
              for app in admin_logado.get("/admin/").context["available_apps"]}
    # Tarefas (integracoes e importacoes) no Nucleo; Integracoes so com a plataforma.
    assert secoes["integracoes"] == ["Shopify"]
    assert "Tarefas" in secoes["core"]
    assert "Politicas de publicacao" not in html
    assert "Estados de publicacao" not in html


@pytest.mark.django_db
def test_salvar_pagina_cria_e_depois_atualiza_a_mesma_configuracao(admin_logado):
    """Salvar novamente precisa editar o singleton sem gerar outra linha para a conta."""
    assert admin_logado.post(URL, _dados()).status_code == 302
    configuracao = ConfiguracaoIntegracao.objects.get()
    assert configuracao.habilitado("receber", "produtos", "get")
    assert configuracao.habilitado("receber", "pedidos", "create")
    assert configuracao.habilitado("enviar", "estoque", "update")

    ConfiguracaoIntegracao.objects.filter(pk=configuracao.pk).update(
        nome="Nome antigo", versao_api="1900-01"
    )
    dados = _dados(
        nome="Tentativa de alterar", versao_api="1900-02", token_acesso="", segredo_app=""
    )
    assert admin_logado.post(URL, dados).status_code == 302
    assert ConfiguracaoIntegracao.objects.count() == 1
    configuracao.refresh_from_db()
    assert configuracao.nome == "Shopify"
    assert configuracao.versao_api == "2026-07"
    assert configuracao.token_acesso == "shpat_token-novo"


@pytest.mark.django_db
def test_usuario_somente_leitura_nao_altera_configuracao(client, conta):
    """A pagina custom deve respeitar change, como um formulario normal do admin."""
    usuario = User.objects.create_user(
        "leitor", "leitor@starhub.test", "senha-forte-123", account=conta, is_staff=True
    )
    usuario.user_permissions.add(Permission.objects.get(
        codename="view_configuracaointegracao",
        content_type__app_label="integracoes",
    ))
    client.force_login(usuario)

    assert client.get(URL).status_code == 200
    assert client.post(URL, _dados()).status_code == 403
    assert not ConfiguracaoIntegracao.objects.exists()
