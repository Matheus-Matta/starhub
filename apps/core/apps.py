from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Nucleo"

    def ready(self):
        from auditlog.models import LogEntry
        from django.db.models.signals import post_migrate, post_save, pre_save

        from apps.core.models import Account
        from apps.core.origem import marcar_log
        from apps.core.perfis_padrao import grupos_depois_do_migrate, perfis_da_conta_nova

        pre_save.connect(marcar_log, sender=LogEntry, dispatch_uid="starhub_origem_do_log")
        # Conta nova nasce com os perfis de acesso iniciais; os grupos fixos ficam em dia
        # com os models a cada migrate (apps/core/perfis_padrao.py).
        post_save.connect(perfis_da_conta_nova, sender=Account, dispatch_uid="starhub_perfis_conta")
        post_migrate.connect(grupos_depois_do_migrate, dispatch_uid="starhub_grupos_fixos")
