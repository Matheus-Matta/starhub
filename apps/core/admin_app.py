# Fica fora de apps.py: la o Django acharia dois AppConfig "default" (o nosso
# CoreConfig e o AdminConfig importado) e recusaria subir.
from django.contrib.admin.apps import AdminConfig


class StarHubAdminConfig(AdminConfig):
    """Troca o admin.site padrao pelo StarHubAdminSite.

    Todo `@admin.register` e `admin.site.register` dos apps cai no site novo,
    sem ninguem precisar importar outro objeto."""

    default_site = "apps.core.admin_site.StarHubAdminSite"
