from django.core.paginator import EmptyPage, Paginator
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, permissions
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.core.models import Account
from apps.core.tenant.context import tenant_context
from apps.loja.catalogo_ia_dados import linhas_catalogo, referencias_catalogo

POR_PAGINA_PADRAO = 1000
POR_PAGINA_MAXIMO = 5000
class LimiteCatalogoPublico(SimpleRateThrottle):
    scope = "catalogo_publico"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class CatalogoPublicoView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    renderer_classes = [TemplateHTMLRenderer]
    throttle_classes = [LimiteCatalogoPublico]
    template_name = "loja/catalogo_ia.html"

    def _numero(self, nome, padrao, maximo=None):
        valor = self.request.query_params.get(nome, str(padrao))
        try:
            numero = int(valor)
        except (TypeError, ValueError) as erro:
            raise exceptions.ValidationError(
                {"erro": f"{nome} precisa ser um numero inteiro."}
            ) from erro
        if numero < 1 or (maximo is not None and numero > maximo):
            limite = f" entre 1 e {maximo}" if maximo else " maior que zero"
            raise exceptions.ValidationError({"erro": f"{nome} precisa ser{limite}."})
        return numero

    def get(self, request, conta_uuid):
        numero_pagina = self._numero("page", 1)
        por_pagina = self._numero("per_page", POR_PAGINA_PADRAO, POR_PAGINA_MAXIMO)
        conta = get_object_or_404(
            Account, pk=conta_uuid, active=True, catalogo_publico=True
        )

        with tenant_context(conta):
            paginador = Paginator(referencias_catalogo(), por_pagina)
            try:
                pagina = paginador.page(numero_pagina)
            except EmptyPage as erro:
                raise exceptions.NotFound("Pagina inexistente.") from erro
            itens = linhas_catalogo(list(pagina.object_list), request)

        resposta = Response({
            "itens": itens,
            "pagina": pagina,
            "por_pagina": por_pagina,
        })
        resposta["X-Catalog-Total"] = str(paginador.count)
        resposta["X-Catalog-Total-Pages"] = str(paginador.num_pages)
        resposta["X-Catalog-Per-Page"] = str(por_pagina)
        resposta["Cache-Control"] = "no-store, max-age=0"
        resposta["Content-Security-Policy"] = (
            "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        resposta["Referrer-Policy"] = "no-referrer"
        resposta["X-Content-Type-Options"] = "nosniff"
        resposta["X-Frame-Options"] = "DENY"
        resposta["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
        return resposta
