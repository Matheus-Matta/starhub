from django.conf import settings
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.template.response import TemplateResponse
from django.urls import path

from apps.core.busca import TAMANHO_MINIMO, buscar
from apps.core.perfil import perfil_view
from apps.core.ui.menu import agrupar_apps, com_minha_conta


class LoginForm(AdminAuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["placeholder"] = "seu.usuario"
        self.fields["password"].widget.attrs["placeholder"] = "Sua senha"


class StarHubAdminSite(admin.AdminSite):
    login_form = LoginForm
    site_header = "StarHub"
    site_title = "StarHub"
    index_title = "Painel"
    # O menu lateral do Django da lugar ao nosso (templates/components/sidebar.html).
    enable_nav_sidebar = False

    def index(self, request, extra_context=None):
        # Import tardio: o admin site carrega antes dos models estarem prontos.
        from apps.loja.painel import montar_painel

        contexto = {"painel": montar_painel(), **(extra_context or {})}
        return super().index(request, extra_context=contexto)

    def get_app_list(self, request, app_label=None):
        apps = super().get_app_list(request, app_label)
        if app_label is not None:  # pagina de UM app: mostra os models dele mesmo
            return apps
        apps = agrupar_apps(apps, getattr(settings, "STARHUB_MENU_AGRUPAR", {}))
        return com_minha_conta(apps, request)

    def get_urls(self):
        extras = [
            path("busca/", self.admin_view(self.busca_view), name="busca"),
            path("perfil/", self.admin_view(lambda request: perfil_view(self, request)),
                 name="perfil"),
            path("relatorios/<str:chave>/", self.admin_view(self.relatorio_view),
                 name="relatorio"),
        ]
        return [*extras, *super().get_urls()]

    def relatorio_view(self, request, chave):
        # Import tardio: o registro de relatorios le os ModelAdmin ja registrados.
        from apps.core.relatorios.views import relatorio_view

        return relatorio_view(self, request, chave)

    def busca_view(self, request):
        termo = request.GET.get("q", "").strip()
        grupos = buscar(request, self, termo)
        contexto = {
            **self.each_context(request),
            "title": "Busca",
            "subtitle": None,
            "termo_busca": termo,
            "grupos": grupos,
            "total": sum(grupo["total"] for grupo in grupos),
            "tamanho_minimo": TAMANHO_MINIMO,
        }
        return TemplateResponse(request, "admin/busca.html", contexto)
