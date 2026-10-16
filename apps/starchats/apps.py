from django.apps import AppConfig


class StarChatsConfig(AppConfig):
    name = "apps.starchats"
    verbose_name = "StarChats"

    def ready(self):
        from apps.starchats import sinais

        sinais.conectar()
