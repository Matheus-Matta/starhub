from django.apps import AppConfig


class NotificacoesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notificacoes"
    verbose_name = "Notificacoes"

    def ready(self):
        from django.db.models.signals import post_save

        from apps.core.models import Account
        from apps.notificacoes import contas, sinais

        sinais.conectar()
        post_save.connect(contas.conta_criada, sender=Account,
                          dispatch_uid="notificacoes_conta_criada")
