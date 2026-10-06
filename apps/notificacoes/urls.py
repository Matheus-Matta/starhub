from django.urls import path

from apps.notificacoes.views import marcar_lidas

urlpatterns = [
    path("marcar-lidas/", marcar_lidas, name="notificacoes_marcar_lidas"),
]
