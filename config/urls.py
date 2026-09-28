from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.woo_api.views.recursos import RaizView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="admin:index", permanent=False)),
    path("admin/", admin.site.urls),
    # Mesmo prefixo do WordPress: o ERP aponta para este dominio como se fosse a loja.
    path("wp-json/", include("apps.woo_api.urls")),
    path("wp-json", RaizView.as_view()),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
