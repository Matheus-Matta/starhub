"""Guia do app Shopify usado para receber e publicar cupons do StarHub."""

from django.template.response import TemplateResponse
from django.urls import reverse


def guia_view(model_admin, request):
    contexto = {
        **model_admin.admin_site.each_context(request),
        "title": "Guia dos cupons na Shopify",
        "subtitle": "Como preparar o app e sincronizar descontos com codigo.",
        "opts": model_admin.model._meta,
        "url_integracao": reverse(
            "admin:integracoes_configuracaointegracao_shopify"),
        "url_cupons": reverse("admin:loja_cupom_changelist"),
    }
    return TemplateResponse(request, "admin/integracoes/guia_cupons.html", contexto)
