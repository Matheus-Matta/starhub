from django.core.paginator import EmptyPage, Paginator
from rest_framework import exceptions, permissions
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle

from apps.loja.catalogo_ia_dados import linhas_catalogo, referencias_catalogo
from apps.woo_api.autenticacao import ChaveCatalogoAuthentication
from apps.woo_api.models import ChaveApi
from apps.woo_api.views.base import WooView

POR_PAGINA_PADRAO = 1000
POR_PAGINA_MAXIMO = 5000
ESCOPO = "catalogo_ia"


class PodeLerCatalogoIa(permissions.BasePermission):
    def has_permission(self, request, view):
        chave = request.auth
        if not isinstance(chave, ChaveApi):
            return False
        if not chave.permite(request.method):
            raise exceptions.AuthenticationFailed("A chave nao tem permissao de leitura.")
        return chave.tem_escopo(ESCOPO)


class LimiteCatalogoIa(SimpleRateThrottle):
    scope = "catalogo_ia"

    def get_cache_key(self, request, view):
        chave_id = getattr(request.auth, "pk", None)
        identidade = f"chave-{chave_id}" if chave_id else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": identidade}


class CatalogoIaView(WooView):
    authentication_classes = [ChaveCatalogoAuthentication]
    permission_classes = [PodeLerCatalogoIa]
    renderer_classes = [TemplateHTMLRenderer]
    throttle_classes = [LimiteCatalogoIa]
    template_name = "loja/catalogo_ia.html"

    def _numero(self, nome, padrao, maximo=None):
        valor = self.request.query_params.get(nome, str(padrao))
        try:
            numero = int(valor)
        except (TypeError, ValueError) as erro:
            raise exceptions.ValidationError(
                f"{nome} precisa ser um numero inteiro."
            ) from erro
        if numero < 1 or (maximo is not None and numero > maximo):
            limite = f" entre 1 e {maximo}" if maximo else " maior que zero"
            raise exceptions.ValidationError(f"{nome} precisa ser{limite}.")
        return numero

    def get(self, request):
        numero_pagina = self._numero("page", 1)
        por_pagina = self._numero("per_page", POR_PAGINA_PADRAO, POR_PAGINA_MAXIMO)

        paginador = Paginator(referencias_catalogo(), por_pagina)
        try:
            pagina = paginador.page(numero_pagina)
        except EmptyPage as erro:
            raise exceptions.NotFound("Pagina inexistente.") from erro

        resposta = Response({
            "itens": linhas_catalogo(list(pagina.object_list), request),
            "pagina": pagina,
            "por_pagina": por_pagina,
        })
        resposta["X-Catalog-Total"] = str(paginador.count)
        resposta["X-Catalog-Total-Pages"] = str(paginador.num_pages)
        resposta["X-Catalog-Per-Page"] = str(por_pagina)
        resposta["Cache-Control"] = "private, no-store, max-age=0"
        resposta["Content-Security-Policy"] = (
            "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        resposta["Referrer-Policy"] = "no-referrer"
        resposta["X-Content-Type-Options"] = "nosniff"
        resposta["X-Frame-Options"] = "DENY"
        resposta["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
        return resposta
