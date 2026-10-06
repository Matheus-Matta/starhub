"""Permissoes da configuracao da propria conta no admin."""

import pytest
from django.urls import reverse

from apps.core.models import AccessProfile, User

pytestmark = pytest.mark.django_db
LISTA = "admin:core_account_changelist"


@pytest.fixture
def administrador(client, conta):
    perfil = AccessProfile.all_objects.get(account=conta, code="administrador")
    usuario = User.objects.create_user(
        "administrador", "admin@loja.test", "senha-forte-123",
        account=conta, access_profile=perfil, is_staff=True,
    )
    client.force_login(usuario)
    return client


def _menu(cliente):
    html = cliente.get(reverse("admin:index")).content.decode()
    return html.split('class="sidebar-menu"')[1].split("</nav>")[0]


def test_menu_leva_direto_a_minha_conta_em_vez_da_lista(administrador, conta):
    """A lista "Contas" tinha uma linha so: o operador clicava duas vezes para chegar."""
    menu = _menu(administrador)

    assert "Minha conta" in menu
    assert reverse("admin:core_account_change", args=[conta.pk]) in menu
    assert f'href="{reverse(LISTA)}"' not in menu


def test_superusuario_ve_minha_conta_e_mantem_a_lista_de_contas(admin_logado, conta):
    """O superusuario cadastra contas novas: tirar a lista do menu esconderia esse fluxo."""
    menu = _menu(admin_logado)

    assert reverse("admin:core_account_change", args=[conta.pk]) in menu
    assert f'href="{reverse(LISTA)}"' in menu


def test_administrador_ve_a_configuracao_da_propria_conta(administrador, conta):
    """O bloqueio antigo escondia a configuracao apesar da permissao do perfil."""
    assert administrador.get(reverse(LISTA)).status_code == 200
    pagina = administrador.get(
        reverse("admin:core_account_change", args=[conta.pk])
    ).content.decode()
    assert 'name="email"' in pagina
    assert 'name="phone"' in pagina
    assert 'name="dominio_avaliacoes"' in pagina


def test_administrador_nao_altera_dados_essenciais_nem_por_post(administrador, conta):
    """Esconder o campo nao basta: um POST manual nao pode mudar dados essenciais."""
    url = reverse("admin:core_account_change", args=[conta.pk])
    resposta = administrador.post(url, {
        "name": "Conta adulterada", "slug": "conta-adulterada",
        "legal_name": "Outra Empresa", "document": "52998224725", "active": "",
        "email": "novo@loja.test", "phone": "+55 11 99999-9999",
        "dominio_avaliacoes": "nova-loja.test", "timezone": "UTC", "currency": "USD",
        "_save": "Salvar",
    })

    assert resposta.status_code == 302
    conta.refresh_from_db()
    assert (conta.email, conta.phone, conta.dominio_avaliacoes) == (
        "novo@loja.test", "+55 11 99999-9999", "nova-loja.test",
    )
    assert (conta.name, conta.slug, conta.legal_name, conta.document) == (
        "Loja Teste", "loja-teste", "", "",
    )
    assert (conta.active, conta.timezone, conta.currency) == (
        True, "America/Sao_Paulo", "BRL",
    )


def test_administrador_nao_abre_conta_de_outro_tenant(
        administrador, outra_conta):
    url = reverse("admin:core_account_change", args=[outra_conta.pk])

    assert administrador.get(url).status_code != 200


def test_superusuario_continua_com_acesso_completo(admin_logado):
    assert reverse(LISTA) in admin_logado.get(reverse("admin:index")).content.decode()
    assert admin_logado.get(reverse(LISTA)).status_code == 200
