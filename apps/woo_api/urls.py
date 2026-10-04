"""Rotas sob /wp-json/. Sem barra no final, como no WordPress; a barra e opcional
(`/?$`) porque um POST redirecionado pelo APPEND_SLASH perderia o corpo."""

from django.urls import re_path

from apps.woo_api.recursos.pedidos import PedidoRecurso
from apps.woo_api.views.jwt import TokenView, ValidarTokenView
from apps.woo_api.views.pedidos_v3 import (
    PedidoDetalheV3View,
    PedidoListaV3View,
    PedidoLoteV3View,
)
from apps.woo_api.views.produtos_v3 import (
    CategoriaDetalheV3View,
    CategoriaListaV3View,
    CategoriaLoteV3View,
    ProdutoDetalheV3View,
    ProdutoListaV3View,
    ProdutoLoteV3View,
)
from apps.woo_api.views.recursos import RECURSOS, IndiceView, RaizView, views_de

urlpatterns = [
    re_path(r"^$", RaizView.as_view(), name="woo_raiz"),
    re_path(r"^jwt-auth/v1/token/?$", TokenView.as_view(), name="jwt_token"),
    re_path(r"^jwt-auth/v1/token/validate/?$", ValidarTokenView.as_view(), name="jwt_validar"),
    re_path(r"^wc/v1/?$", IndiceView.as_view(), name="woo_indice"),
    re_path(
        r"^wc/v3/products/categories/?$",
        CategoriaListaV3View.as_view(),
        name="woo_v3_categories",
    ),
    re_path(
        r"^wc/v3/products/categories/batch/?$",
        CategoriaLoteV3View.as_view(),
        name="woo_v3_categories_lote",
    ),
    re_path(
        r"^wc/v3/products/categories/(?P<pk>\d+)/?$",
        CategoriaDetalheV3View.as_view(),
        name="woo_v3_categories_detalhe",
    ),
    re_path(r"^wc/v3/products/?$", ProdutoListaV3View.as_view(), name="woo_v3_products"),
    re_path(
        r"^wc/v3/products/batch/?$", ProdutoLoteV3View.as_view(), name="woo_v3_products_lote"
    ),
    re_path(
        r"^wc/v3/products/(?P<pk>\d+)/?$",
        ProdutoDetalheV3View.as_view(),
        name="woo_v3_products_detalhe",
    ),
    re_path(r"^wc/v3/orders/?$", PedidoListaV3View.as_view(), name="woo_v3_orders"),
    re_path(r"^wc/v3/orders/batch/?$", PedidoLoteV3View.as_view(), name="woo_v3_orders_lote"),
    re_path(
        r"^wc/v3/orders/(?P<pk>\d+)/?$",
        PedidoDetalheV3View.as_view(),
        name="woo_v3_orders_detalhe",
    ),
]

# Categorias antes de produtos nao e preciso: o <pk> so casa numero.
for caminho, recurso in RECURSOS.items():
    lista, detalhe, lote = views_de(recurso)
    if recurso is PedidoRecurso:
        # Pedido so le e atualiza: v1 usa as mesmas views (e a mesma regra) da v3.
        lista = PedidoListaV3View.as_view()
        detalhe = PedidoDetalheV3View.as_view()
        lote = PedidoLoteV3View.as_view()
    nome = caminho.replace("/", "_")
    urlpatterns += [
        re_path(rf"^wc/v1/{caminho}/?$", lista, name=f"woo_{nome}"),
        re_path(rf"^wc/v1/{caminho}/batch/?$", lote, name=f"woo_{nome}_lote"),
        re_path(rf"^wc/v1/{caminho}/(?P<pk>\d+)/?$", detalhe, name=f"woo_{nome}_detalhe"),
    ]
