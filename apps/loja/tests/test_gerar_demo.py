"""python manage.py gerar_demo: 10+ registros por model, imagens demo em categoria e
produto, e --limpar/--remover mexendo so no que o demo criou."""

from io import StringIO

import pytest
from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.models import AccessProfile, Account, User
from apps.core.tenant.context import tenant_context
from apps.core.validators import validar_cnpj, validar_cpf
from apps.loja.models import Categoria, Cliente, MidiaProduto, Produto, Tag, TipoVariante

pytestmark = [pytest.mark.django_db, pytest.mark.sem_conta]


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    # A foto demo das avaliacoes e gravada no MEDIA: fora da pasta media/ do projeto.
    settings.MEDIA_ROOT = tmp_path


def _gerar(conta, *extras):
    saida = StringIO()
    call_command("gerar_demo", "--conta", conta.slug, "--permitir-producao", *extras, stdout=saida)
    return saida.getvalue()


def _modelos_com_conta():
    return [m for m in apps.get_models()
            if m._meta.app_label in ("core", "loja", "woo_api") and hasattr(m, "all_objects")
            and not m.__name__.startswith("Historical")]


def test_gera_ao_menos_dez_de_cada_model_com_imagens(conta):
    saida = _gerar(conta)
    for modelo in _modelos_com_conta():
        assert modelo.all_objects.filter(account=conta).count() >= 10, modelo.__name__
    assert User.objects.filter(account=conta).count() >= 10
    assert Account.objects.count() >= 10
    assert all("/static/starhub/img/demos/demo" in c.imagem["src"]
               for c in Categoria.all_objects.filter(account=conta))
    assert all("/static/starhub/img/demos/demo" in m.url
               for m in MidiaProduto.all_objects.filter(account=conta))
    for cliente in Cliente.all_objects.filter(account=conta):
        validar_cpf(cliente.cpf)  # levanta ValidationError se o digito estiver errado
        validar_cnpj(cliente.cnpj)
    assert set(Produto.all_objects.values_list("tipo", flat=True)) == {
        "simple", "variable", "bundle", "external"
    }
    assert "ck_" in saida and "Demo gerado" in saida


def test_limpar_recria_e_remover_apaga_so_o_demo(conta):
    with tenant_context(conta):
        minha_tag = Tag.objects.create(nome="Minha tag")
        cor = TipoVariante.objects.create(nome="Cor")
    _gerar(conta)
    produtos = Produto.all_objects.filter(account=conta).count()
    with pytest.raises(CommandError, match="ja tem dados demo"):
        _gerar(conta)
    _gerar(conta, "--limpar")
    assert Produto.all_objects.filter(account=conta).count() == produtos
    _gerar(conta, "--remover")
    for modelo in _modelos_com_conta():
        restantes = modelo.all_objects.filter(account=conta)
        if modelo is Tag:
            assert list(restantes) == [minha_tag]
        elif modelo is TipoVariante:
            assert list(restantes) == [cor]  # o demo reaproveitou "Cor" e nao o apagou
        elif modelo is AccessProfile:
            assert not restantes.filter(is_system=False).exists()  # os fixos sao da conta
        else:
            assert not restantes.exists(), modelo.__name__
    assert list(Account.objects.all()) == [conta]
    assert not User.objects.filter(account=conta).exists()


def test_recusa_sem_debug_e_conta_inexistente(conta, settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="producao"):
        call_command("gerar_demo", "--conta", conta.slug, stdout=StringIO())
    with pytest.raises(CommandError, match="nao encontrada"):
        call_command("gerar_demo", "--conta", "nao-existe", "--permitir-producao",
                     stdout=StringIO())
