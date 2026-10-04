"""Grupos fixos (migration core.0003 + post_migrate) e perfis iniciais de toda conta
(sinal post_save de Account). Regras em apps/core/perfis_padrao.py."""

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command

from apps.core.models import AccessProfile, Account, User
from apps.core.perfis_padrao import GRUPOS, criar_perfis, nome_do_grupo, sincronizar_grupos

pytestmark = pytest.mark.django_db
CODIGOS = {codigo for codigo, _, _, _ in GRUPOS}


def _perms(nome):
    grupo = Group.objects.get(name=nome_do_grupo(nome))
    return {f"{p.content_type.app_label}.{p.codename}"
            for p in grupo.permissions.select_related("content_type")}


def test_grupos_fixos_existem_com_as_permissoes_de_cada_papel():
    assert Group.objects.filter(name__startswith="Padrao: ").count() == len(GRUPOS)
    vendas = _perms("Vendas")
    assert {"loja.change_pedido", "loja.add_cliente", "loja.view_produto"} <= vendas
    assert "loja.delete_produto" not in vendas and "loja.change_produto" not in vendas
    admin = _perms("Administrador")
    assert {"woo_api.usar_api", "auditlog.view_logentry", "core.add_user"} <= admin
    assert "core.add_account" not in admin  # conta nova e do superusuario
    assert all(p.split(".")[1].startswith("view_") for p in _perms("Somente leitura"))
    assert not any("historical" in p for p in admin)


def test_conta_nova_nasce_com_um_perfil_de_cada_grupo_fixo(conta, outra_conta):
    # outra_conta e criada com a conta ativa sendo `conta`: o perfil vai para a nova.
    for dona in (conta, outra_conta):
        perfis = AccessProfile.all_objects.filter(account=dona, is_system=True)
        assert set(perfis.values_list("code", flat=True)) == CODIGOS
    nova = Account.objects.create(name="Loja Nova", slug="loja-nova")
    assert AccessProfile.all_objects.filter(account=nova, is_system=True).count() == len(GRUPOS)


def test_usuario_com_perfil_fixo_ganha_as_permissoes_do_grupo(conta):
    perfil = AccessProfile.all_objects.get(account=conta, code="vendas")
    usuario = User.objects.create_user("vendedor", "v@loja.test", "senha-forte-123",
                                       account=conta, is_staff=True, access_profile=perfil)
    assert usuario.has_perm("loja.change_pedido")
    assert not usuario.has_perm("loja.delete_produto")


def test_criar_perfis_repoe_o_que_falta_sem_duplicar(conta):
    AccessProfile.all_objects.filter(account=conta, code="estoque").delete()
    criar_perfis(conta.pk)
    criar_perfis(conta.pk)
    perfis = AccessProfile.all_objects.filter(account=conta, is_system=True)
    assert perfis.count() == len(GRUPOS) and perfis.filter(code="estoque").exists()


def test_sincronizar_devolve_a_permissao_tirada_e_tira_a_sobrando():
    grupo = Group.objects.get(name=nome_do_grupo("Vendas"))
    mudar_pedido = Permission.objects.get(codename="change_pedido")
    apagar_produto = Permission.objects.get(codename="delete_produto")
    grupo.permissions.remove(mudar_pedido)
    grupo.permissions.add(apagar_produto)
    sincronizar_grupos()
    assert grupo.permissions.filter(pk=mudar_pedido.pk).exists()
    assert not grupo.permissions.filter(pk=apagar_produto.pk).exists()


def test_admin_nao_exclui_nem_troca_grupo_de_perfil_do_sistema(admin_logado, conta):
    perfil = AccessProfile.all_objects.get(account=conta, code="gerente")
    url = f"/admin/core/accessprofile/{perfil.pk}/"
    assert admin_logado.get(f"{url}delete/").status_code == 403
    pagina = admin_logado.get(f"{url}change/").content.decode()
    assert 'name="group"' not in pagina and 'name="code"' not in pagina
    assert 'name="name"' in pagina  # o nome da para ajustar


def test_post_migrate_recria_os_grupos_fixos():
    """Roda no ultimo app COM models (o corsheaders, ultimo da lista em dev, nao tem)."""
    AccessProfile.all_objects.filter(is_system=True).delete()  # o perfil protege o grupo
    Group.objects.filter(name__startswith="Padrao: ").delete()
    call_command("migrate", verbosity=0)
    assert Group.objects.filter(name__startswith="Padrao: ").count() == len(GRUPOS)
