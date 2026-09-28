"""Admin para dois publicos: usuario comum (so a conta dele, sem campo conta) e
superusuario (todas as contas, escolhe a conta ao criar)."""

import re

import pytest
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from rest_framework.test import APIClient

from apps.core.models import User
from apps.core.tenant.context import tenant_context, ve_todas_as_contas
from apps.core.tenant.middleware import TenantMiddleware
from apps.loja.models import Cliente, Pedido, Produto, VarianteProduto
from apps.loja.services.variantes import criar_produto

pytestmark = [pytest.mark.django_db, pytest.mark.sem_conta]


@pytest.fixture
def produtos(conta, outra_conta):
    with tenant_context(conta):
        nosso = criar_produto("Produto da casa", sku="CASA-1")
    with tenant_context(outra_conta):
        deles = criar_produto("Produto de fora", sku="FORA-1")
    return nosso, deles


@pytest.fixture
def usuario_comum(client, conta):
    usuario = User.objects.create_user(
        "operador", "op@loja.test", "senha-forte-123", account=conta, is_staff=True
    )
    usuario.user_permissions.set(Permission.objects.filter(content_type__app_label="loja"))
    usuario.user_permissions.add(*Permission.objects.filter(codename__endswith="_user"))
    client.force_login(usuario)
    return client


def _produto(**extra):
    dados = {"nome": "Novo", "slug": "novo", "tipo": "simple", "status": "publish",
             "visibilidade": "visible", "atributos": "[]", "metadados": "[]",
             "ordem_menu": "0", "id_pai": "0", **extra}
    for prefixo in ("variantes", "tipos_variante", "midias", "componentes"):
        dados.update({f"{prefixo}-TOTAL_FORMS": "0", f"{prefixo}-INITIAL_FORMS": "0"})
    return dados


def _erros(resposta):
    """Erros do form e dos inlines, para a falha dizer o motivo e nao despejar o HTML."""
    contexto = resposta.context or {}
    form = contexto.get("adminform")
    inlines = contexto.get("inline_admin_formsets") or []
    return {
        "form": form.form.errors if form else None,
        "inlines": [(i.formset.errors, i.formset.non_form_errors()) for i in inlines],
    }


def test_usuario_comum_ve_so_a_conta_dele_e_sem_coluna_conta(usuario_comum, produtos):
    html = usuario_comum.get("/admin/loja/produto/").content.decode()
    assert "Produto da casa" in html and "Produto de fora" not in html
    assert "field-account" not in html


def test_usuario_comum_nao_ve_nem_troca_a_conta_ao_criar(usuario_comum, conta, outra_conta):
    """O campo nem existe no form: mandar account na mao (DevTools) nao adianta."""
    assert 'name="account"' not in usuario_comum.get("/admin/loja/produto/add/").content.decode()
    resposta = usuario_comum.post("/admin/loja/produto/add/", _produto(account=outra_conta.pk))
    assert resposta.status_code == 302, _erros(resposta)
    produto = Produto.all_objects.get(nome="Novo")
    assert produto.account_id == conta.pk
    assert not VarianteProduto.all_objects.filter(produto=produto).exists()


def test_usuario_comum_so_lista_usuarios_da_conta_dele(usuario_comum, outra_conta):
    User.objects.create_user("de-fora", "fora@outra.test", "senha-forte-123", account=outra_conta)
    html = usuario_comum.get("/admin/core/user/").content.decode()
    assert "de-fora" not in html and "operador" in html


def test_superusuario_ve_todas_as_contas_com_coluna_e_filtro(admin_logado, produtos):
    html = admin_logado.get("/admin/loja/produto/").content.decode()
    assert "Produto da casa" in html and "Produto de fora" in html
    assert "field-account" in html and "Outra Loja" in html
    assert "account__id__exact" in html  # filtro "Conta" na gaveta


def test_superusuario_cria_registro_em_outra_conta(admin_logado, conta, outra_conta):
    form = admin_logado.get("/admin/loja/produto/add/").content.decode()
    assert 'name="account"' in form
    assert f'value="{conta.pk}" selected' in form  # comeca na conta dele
    resposta = admin_logado.post(
        "/admin/loja/produto/add/", _produto(account=outra_conta.pk, origin="import")
    )
    assert resposta.status_code == 302, _erros(resposta)
    produto = Produto.all_objects.get(nome="Novo")
    assert (produto.account_id, produto.origin) == (outra_conta.pk, "import")
    # Variante criada depois (modal) herda a conta do produto, nao a do superusuario.
    with tenant_context(outra_conta):
        variante = VarianteProduto.objects.create(produto=produto, titulo="Default")
    assert (variante.account_id, variante.is_default) == (outra_conta.pk, True)


def test_superusuario_ve_a_conta_mas_nao_troca_depois_de_criado(admin_logado, produtos):
    _, deles = produtos
    html = admin_logado.get(f"/admin/loja/produto/{deles.pk}/change/").content.decode()
    assert 'name="account"' not in html and "Outra Loja" in html


def test_relacao_com_outra_conta_vira_erro_no_campo(admin_logado, conta, outra_conta):
    """O select mostra clientes de todas as contas; escolher o errado nao pode dar 500."""
    with tenant_context(conta):
        cliente = Cliente.objects.create(email="ana@casa.test")
    dados = {"account": outra_conta.pk, "number": "SH-1", "status": "pending", "moeda": "BRL",
             "financial_status": "pending", "fulfillment_status": "unfulfilled",
             "cliente": cliente.pk, "linhas_frete": "[]",
             "linhas_taxa": "[]", "linhas_cupom": "[]", "metadados": "[]"}
    for prefixo in ("itens", "pagamentos", "entregas"):
        dados.update({f"{prefixo}-TOTAL_FORMS": "0", f"{prefixo}-INITIAL_FORMS": "0"})
    resposta = admin_logado.post("/admin/loja/pedido/add/", dados)
    assert resposta.status_code == 200
    assert "Pertence a outra conta." in resposta.content.decode()
    assert not Pedido.all_objects.exists()


def test_superusuario_so_ve_todas_as_contas_dentro_do_admin(conta):
    """Na API (e fora do admin) o superusuario fica na conta dele, como todo mundo."""
    usuario = User.objects.create_superuser("root", "r@x.test", "senha-forte-123", account=conta)
    vistos = {}

    def view(request):
        vistos[request.path] = ve_todas_as_contas()
        from django.http import HttpResponse

        return HttpResponse("ok")

    for caminho in ("/admin/loja/produto/", "/wp-json/wc/v1/products"):
        request = RequestFactory().get(caminho)
        request.user = usuario
        TenantMiddleware(view)(request)
    assert vistos == {"/admin/loja/produto/": True, "/wp-json/wc/v1/products": False}


def test_superusuario_na_api_ve_so_a_propria_conta(conta, produtos):
    nosso, _ = produtos
    User.objects.create_superuser("root", "r@x.test", "senha-forte-123", account=conta)
    cliente = APIClient()
    token = cliente.post("/wp-json/jwt-auth/v1/token", {
        "username": "root", "password": "senha-forte-123"}, format="json").json()["token"]
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert [p["id"] for p in cliente.get("/wp-json/wc/v1/products").json()] == [nosso.pk]


def test_origem_e_conta_ficam_ocultas_para_usuario_comum(usuario_comum):
    html = usuario_comum.get("/admin/loja/cliente/add/").content.decode()
    assert 'name="origin"' not in html and 'name="account"' not in html


def test_origem_fica_na_secao_conta_do_superusuario(admin_logado):
    resposta = admin_logado.get("/admin/loja/cliente/add/")
    html = resposta.content.decode()
    secao = re.split(r'fieldset-heading">\s*Conta', html, maxsplit=1)[1].split("</fieldset>")[0]
    assert 'name="account"' in secao and 'name="origin"' in secao
