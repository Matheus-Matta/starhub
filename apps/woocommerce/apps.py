from django.apps import AppConfig


class WoocommerceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.woocommerce"
    verbose_name = "WooCommerce"

    def ready(self):
        # Registra o WooCommerce como destino do envio (envio/registro.py).
        from apps.woocommerce import frete_sinais
        from apps.woocommerce.envio import marketplace  # noqa: F401

        frete_sinais.conectar()
