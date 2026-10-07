from django.contrib.auth.models import Permission

from apps.core.models import User


def test_sidebar_em_secoes_com_chaves_de_api_junto_dos_usuarios(admin_logado):
    html = admin_logado.get("/admin/").content.decode()
    menu = html.split('class="sidebar-menu"')[1].split("</nav>")[0]
    assert "API WooCommerce" not in menu
    assert "Guia da API" not in menu
    # Chave de API e credencial da conta: fica na secao de contas e usuarios (core).
    secao_auth = menu.split("Nucleo")[1].split('class="menu-secao"')[0]
    assert "/admin/core/user/" in secao_auth
    assert "/admin/woo_api/chaveapi/" in secao_auth
    assert "<details" not in secao_auth  # secao fixa; dropdown so o de Relatorios
    assert "#key-round" in secao_auth  # icone no item


def test_sidebar_prioriza_loja_e_deixa_auditoria_no_final(admin_logado):
    """O menu deve seguir o fluxo operacional, deixando auditoria por ultimo."""
    html = admin_logado.get("/admin/").content.decode()
    menu = html.split('class="sidebar-menu"')[1].split("</nav>")[0]

    posicoes = [menu.index(nome) for nome in ("Loja", "Integracoes", "Nucleo", "Auditoria")]
    assert posicoes == sorted(posicoes)


def test_header_sem_botao_de_modulos(admin_logado):
    html = admin_logado.get("/admin/").content.decode()
    assert 'aria-label="Modulos"' not in html


def test_busca_da_tabela_sem_botao_e_com_envio_automatico(admin_logado):
    html = admin_logado.get("/admin/loja/produto/").content.decode()
    busca = html.split('id="changelist-search"')[1].split("</form>")[0]
    assert "data-busca-automatica" in busca
    assert "<button" not in busca


def test_perfil_mostra_so_nome_sobrenome_e_email(admin_logado):
    html = admin_logado.get("/admin/perfil/").content.decode()
    for campo in ("first_name", "last_name", "email"):
        assert f'name="{campo}"' in html
    for campo in ("is_superuser", "user_permissions", "groups", "is_staff", "username"):
        assert f'name="{campo}"' not in html


def test_perfil_salva_e_recusa_email_de_outro_usuario(admin_logado, conta):
    User.objects.create_user("outro", "outro@a.test", "senha-forte-123", account=conta)
    resposta = admin_logado.post("/admin/perfil/", {"first_name": "Ana", "last_name": "S",
                                                   "email": "OUTRO@a.test"})
    assert "ja e usado por outro usuario" in resposta.content.decode()
    resposta = admin_logado.post("/admin/perfil/", {"first_name": "Ana", "last_name": "S",
                                                   "email": "ana@a.test"})
    assert resposta.status_code == 302
    assert User.objects.get(username="admin").first_name == "Ana"


def test_perfil_abre_para_equipe_sem_permissao_de_usuarios(client, conta):
    """Antes o link levava a tela de usuarios, que exige auth.change_user."""
    pessoa = User.objects.create_user(
        "vendas", "v@a.test", "senha-forte-123", is_staff=True, account=conta
    )
    pessoa.user_permissions.add(Permission.objects.get(codename="view_produto"))
    client.force_login(pessoa)
    assert client.get("/admin/perfil/").status_code == 200
