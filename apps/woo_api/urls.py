"""Rotas sob /wp-json/. Sem barra no final, como no WordPress; a barra e opcional
(`/?$`) porque um POST redirecionado pelo APPEND_SLASH perderia o corpo."""

from django.urls import re_path

from apps.woo_api.views.jwt import TokenView, ValidarTokenView
from apps.woo_api.views.recursos import RECURSOS, IndiceView, RaizView, views_de

urlpatterns = [
    re_path(r"^$", RaizView.as_view(), name="woo_raiz"),
    re_path(r"^jwt-auth/v1/token/?$", TokenView.as_view(), name="jwt_token"),
    re_path(r"^jwt-auth/v1/token/validate/?$", ValidarTokenView.as_view(), name="jwt_validar"),
    re_path(r"^wc/v1/?$", IndiceView.as_view(), name="woo_indice"),
]

# Categorias antes de produtos nao e preciso: o <pk> so casa numero.
for caminho, recurso in RECURSOS.items():
    lista, detalhe, lote = views_de(recurso)
    nome = caminho.replace("/", "_")
    urlpatterns += [
        re_path(rf"^wc/v1/{caminho}/?$", lista, name=f"woo_{nome}"),
        re_path(rf"^wc/v1/{caminho}/batch/?$", lote, name=f"woo_{nome}_lote"),
        re_path(rf"^wc/v1/{caminho}/(?P<pk>\d+)/?$", detalhe, name=f"woo_{nome}_detalhe"),
    ]
