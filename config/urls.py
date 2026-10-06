from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.woo_api.views.recursos import RaizView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="admin:index", permanent=False)),
    path("admin/", admin.site.urls),
    path("integracoes/shopify/", include("apps.shopify.urls")),
    path("integracoes/woocommerce/", include("apps.woocommerce.urls")),
    path("integracoes/suri/", include("apps.suri.urls")),
    path("notificacoes/", include("apps.notificacoes.urls")),
    # Mesmo prefixo do WordPress: o ERP aponta para este dominio como se fosse a loja.
    path("wp-json/", include("apps.woo_api.urls")),
    path("wp-json", RaizView.as_view()),
]

if settings.DEBUG or getattr(settings, "SERVIR_MEDIA", False):
    # Prod sem nginx na frente (SERVIR_MEDIA=1): a Shopify baixa as fotos das avaliacoes
    # pela URL do hub. static() so funciona em DEBUG, por isso a view direta.
    from django.urls import re_path
    from django.views.static import serve

    prefixo = settings.MEDIA_URL.lstrip("/")
    urlpatterns += [re_path(rf"^{prefixo}(?P<path>.*)$", serve,
                            {"document_root": settings.MEDIA_ROOT})]
