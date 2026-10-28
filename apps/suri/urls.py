from django.urls import path, re_path

from apps.suri.logistica_api import consultar_logistica
from apps.suri.views import webhook, webhook_sem_uuid

urlpatterns = [
    # uuid: o id inteiro deixaria testar as lojas em sequencia (1, 2, 3...).
    path("webhook/<uuid:configuracao_uuid>/", webhook, name="suri_webhook"),
    # Sem a barra tambem: POST nao segue o redirect do APPEND_SLASH.
    re_path(r"^webhook/?$", webhook_sem_uuid, name="suri_webhook_sem_uuid"),
    path("logistica/<uuid:configuracao_uuid>/", consultar_logistica, name="suri_logistica"),
]
