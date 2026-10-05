from django.apps import AppConfig


class SuriConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.suri"
    verbose_name = "Suri Shop"

    def ready(self):
        from apps.suri.envio import marketplace  # noqa: F401
