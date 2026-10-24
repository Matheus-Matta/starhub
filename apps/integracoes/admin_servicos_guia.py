"""Pagina "Guia dos servicos" da Shopify: o passo a passo com os enderecos desta loja.

O trecho do tema sai pronto para colar: URL da consulta (com o UUID da configuracao)
e o script/estilo servidos pelo hub. O host e o da URL publica dos webhooks, porque o
admin pode estar em localhost e o tema precisa de um endereco que a loja alcance.
"""

from urllib.parse import urljoin

from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.templatetags.static import static
from django.urls import reverse

from apps.integracoes.models import ConfiguracaoIntegracao

TRECHO = """{{%- comment -%}} StarHub: servicos do produto (Guia dos servicos) {{%- endcomment -%}}
<div data-starhub-servicos data-titulo="Servicos"
     data-url="{consulta}"
     data-produto="{{{{ product.id }}}}"></div>
<link rel="stylesheet" href="{estilo}">
<script src="{script}" defer></script>"""


def trecho_do_tema(configuracao, endereco_atual):
    base = configuracao.url_webhook or endereco_atual
    return TRECHO.format(
        consulta=urljoin(base, reverse("shopify_servicos_publico", args=[configuracao.uuid])),
        estilo=urljoin(base, static("starhub/shopify/servicos-tema.css")),
        script=urljoin(base, static("starhub/shopify/servicos-tema.js")))


def guia_view(model_admin, request):
    configuracao = ConfiguracaoIntegracao.objects.filter(
        plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY).first()
    if configuracao is None:
        # Sem a configuracao salva nao ha UUID para a consulta do tema.
        return HttpResponseRedirect(reverse("admin:integracoes_configuracaointegracao_shopify"))
    contexto = {
        **model_admin.admin_site.each_context(request),
        "title": "Guia dos servicos na Shopify",
        "subtitle": "Como oferecer os servicos do hub na pagina do produto.",
        "opts": model_admin.model._meta,
        "configuracao": configuracao,
        "trecho": trecho_do_tema(configuracao, request.build_absolute_uri("/")),
        "url_integracao": reverse("admin:integracoes_configuracaointegracao_shopify"),
        "url_servicos": reverse("admin:loja_servico_changelist"),
    }
    return TemplateResponse(request, "admin/integracoes/guia_servicos.html", contexto)
