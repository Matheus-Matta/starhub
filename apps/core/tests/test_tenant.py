import pytest
from django.contrib.auth.models import Group, Permission
from django.http import HttpResponse

from apps.core.models import AccessProfile, Account, Address, User
from apps.core.services.rules import matches_rules
from apps.core.tenant.context import get_current_account_id, tenant_context
from apps.core.tenant.exceptions import TenantContextMissing, TenantMismatchError
from apps.core.tenant.middleware import TenantMiddleware, validate_tenant_response

# Estes testes controlam a conta ativa na mao: sem a conta padrao do conftest.
pytestmark = pytest.mark.sem_conta


@pytest.fixture
def contas(db):
    return (
        Account.objects.create(name="Conta A", slug="conta-a"),
        Account.objects.create(name="Conta B", slug="conta-b"),
    )


@pytest.mark.django_db
def test_manager_isola_consulta_criacao_atualizacao_e_exclusao(contas):
    """Nenhuma operacao normal pode atingir registros de outra conta."""
    conta_a, conta_b = contas
    with tenant_context(conta_a):
        endereco_a = Address.objects.create(name="A")
    with tenant_context(conta_b):
        endereco_b = Address.objects.create(name="B")
        assert list(Address.objects.values_list("name", flat=True)) == ["B"]
        assert Address.objects.filter(pk=endereco_a.pk).update(name="invadido") == 0
        assert Address.objects.filter(pk=endereco_a.pk).delete()[0] == 0
    endereco_a.refresh_from_db()
    endereco_b.refresh_from_db()
    assert endereco_a.name == "A"
    assert endereco_b.account_id == conta_b.pk


@pytest.mark.django_db
def test_manager_exige_contexto_e_impede_troca_de_conta(contas):
    conta_a, conta_b = contas
    with pytest.raises(TenantContextMissing):
        list(Address.objects.all())
    with tenant_context(conta_a):
        with pytest.raises(TenantMismatchError):
            Address.objects.create(account=conta_b, name="Invasao")
        endereco = Address.objects.create(name="Correto")
        with pytest.raises(TenantMismatchError):
            Address.objects.filter(pk=endereco.pk).update(account=conta_b)


@pytest.mark.django_db
def test_manager_protege_operacoes_em_lote(contas):
    conta_a, conta_b = contas
    with tenant_context(conta_a):
        criados = Address.objects.bulk_create([Address(name="Um"), Address(name="Dois")])
        assert all(obj.account_id == conta_a.pk for obj in criados)
        criados[0].name = "Alterado"
        Address.objects.bulk_update(criados, ["name"])
        with pytest.raises(TenantMismatchError):
            Address.objects.bulk_create([Address(account=conta_b, name="Invasao")])
        with pytest.raises(TenantMismatchError):
            Address.objects.bulk_update(criados, ["account"])


@pytest.mark.django_db
def test_middleware_define_e_limpa_contexto_da_conta(contas, rf):
    conta_a, _ = contas
    with tenant_context(conta_a):
        user = User.objects.create_user("ana", password="senha-forte-123")
    observed = []

    def view(request):
        observed.append(get_current_account_id())
        return HttpResponse("ok")

    request = rf.get("/")
    request.user = user
    response = TenantMiddleware(view)(request)
    assert response.status_code == 200
    assert observed == [conta_a.pk]
    assert get_current_account_id(required=False) is None


@pytest.mark.django_db
def test_middleware_rejeita_objeto_de_outra_conta_na_resposta(contas):
    conta_a, conta_b = contas
    with tenant_context(conta_b):
        endereco_b = Address.objects.create(name="Vazamento")
    response = HttpResponse("nao importa")
    response.tenant_objects = [endereco_b]
    with pytest.raises(TenantMismatchError):
        validate_tenant_response(response, conta_a.pk)


@pytest.mark.django_db
def test_perfil_de_acesso_fornece_permissoes_do_group(contas):
    conta_a, _ = contas
    group = Group.objects.create(name="Conta A - viewer")
    permission = Permission.objects.get(codename="view_account")
    group.permissions.add(permission)
    with tenant_context(conta_a):
        profile = AccessProfile.objects.create(name="Viewer", code="viewer", group=group)
        user = User.objects.create_user(
            "viewer", password="senha-forte-123", access_profile=profile
        )
    assert user.has_perm("core.view_account")


def test_motor_de_regras_avalia_apenas_operadores_permitidos():
    rules = {"all": [
        {"field": "active", "operator": "eq", "value": True},
        {"field": "metadata.channel", "operator": "eq", "value": "shopify"},
    ]}
    assert matches_rules({"active": True, "metadata": {"channel": "shopify"}}, rules)


@pytest.mark.django_db
def test_resposta_com_queryset_fatiado_e_conferida_linha_a_linha(contas):
    """O painel entrega querysets com [:6]; exclude() numa fatia levanta TypeError."""
    conta_a, conta_b = contas
    with tenant_context(conta_b):
        Address.objects.create(name="Vazamento")
    response = HttpResponse("nao importa")
    response.context_data = {"lista": Address.all_objects.all()[:6]}
    with pytest.raises(TenantMismatchError):
        validate_tenant_response(response, conta_a.pk)
