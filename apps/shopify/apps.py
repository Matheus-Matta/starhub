from django.apps import AppConfig


class ShopifyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.shopify"
    verbose_name = "Shopify"

    def ready(self):
        # Registra o Shopify no apps.integracoes.envio.registro: sem isso o distribuidor
        # nao acha a plataforma e nenhuma alteracao do hub chega a loja.
        from apps.shopify.envio import marketplace  # noqa: F401
