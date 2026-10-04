"""Grupos fixos do sistema (com as permissoes) e os perfis iniciais das contas que
ja existem. A lista e as regras ficam em apps/core/perfis_padrao.py; conta criada
depois ganha os perfis pelo sinal post_save.

Num banco novo as permissoes so nascem no post_migrate, DEPOIS das migrations:
aqui elas sao criadas antes, para o grupo nao nascer vazio.
"""

from django.contrib.auth.management import create_permissions
from django.contrib.contenttypes.management import create_contenttypes
from django.db import migrations

from apps.core.perfis_padrao import GRUPOS, criar_perfis, nome_do_grupo, sincronizar_grupos


def _garantir_permissoes(apps):
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_contenttypes(app_config, apps=apps, verbosity=0)
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None


def criar(apps, schema_editor):
    _garantir_permissoes(apps)
    sincronizar_grupos(apps)
    for conta_id in apps.get_model("core", "Account").objects.values_list("pk", flat=True):
        criar_perfis(conta_id, apps)


def desfazer(apps, schema_editor):
    AccessProfile = apps.get_model("core", "AccessProfile")
    Group = apps.get_model("auth", "Group")
    nomes = [nome_do_grupo(nome) for _, nome, _, _ in GRUPOS]
    # So os perfis do sistema sem usuario: os em uso ficam (o grupo deles tambem).
    AccessProfile.objects.filter(is_system=True, group__name__in=nomes, users__isnull=True).delete()
    Group.objects.filter(name__in=nomes, access_profiles__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_rotulos_ptbr"),
        ("loja", "0005_remove_opcoes_variante"),
        ("woo_api", "0002_rotulos_ptbr"),
        ("auditlog", "0017_add_actor_email"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [migrations.RunPython(criar, desfazer)]
