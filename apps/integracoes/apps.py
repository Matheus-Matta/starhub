from django.apps import AppConfig


class IntegracoesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integracoes"
    verbose_name = "Integracoes"

    def ready(self):
        from apps.integracoes import orfas, registros_tarefa, sinais

        sinais.conectar()
        orfas.ligar()
        registros_tarefa.ligar()
