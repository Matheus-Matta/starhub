from django.urls import path

from apps.suri.logistica_api import consultar_logistica
from apps.suri.views import webhook

urlpatterns = [
    # uuid: o id inteiro deixaria testar as lojas em sequencia (1, 2, 3...).
    path("webhook/<uuid:configuracao_uuid>/", webhook, name="suri_webhook"),
    path("logistica/<uuid:configuracao_uuid>/", consultar_logistica, name="suri_logistica"),
]
