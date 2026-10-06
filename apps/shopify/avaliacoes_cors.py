"""Origem do tema para a API de avaliacoes, definida na conta da integracao."""

import re

from asgiref.sync import iscoroutinefunction, markcoroutinefunction, sync_to_async
from corsheaders.defaults import default_headers
from corsheaders.middleware import CorsMiddleware
from django.http import HttpResponse, JsonResponse
from django.utils.cache import patch_vary_headers

from apps.integracoes.models import ConfiguracaoIntegracao

ROTA = re.compile(r"/integracoes/shopify/avaliacoes/([0-9]+)/")


class CorsPadraoSemAvaliacoes(CorsMiddleware):
    def is_enabled(self, request):
        return not ROTA.fullmatch(request.path_info) and super().is_enabled(request)


def _origem_permitida(configuracao_id, origem):
    configuracao = ConfiguracaoIntegracao.all_objects.select_related("account").filter(
        pk=configuracao_id, plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY,
        active=True, account__active=True,
    ).first()
    if configuracao is None:
        return False
    dominio = configuracao.account.dominio_avaliacoes.strip().lower()
    return bool(dominio) and origem.lower() == f"https://{dominio}"


def _negada():
    resposta = JsonResponse({
        "erro": "origem_nao_permitida",
        "mensagem": "Dominio nao autorizado para enviar avaliacoes.",
    }, status=403)
    patch_vary_headers(resposta, ("Origin",))
    return resposta


def _preflight():
    resposta = HttpResponse(status=204)
    resposta["Access-Control-Allow-Methods"] = "GET, POST"
    resposta["Access-Control-Allow-Headers"] = ", ".join(default_headers)
    resposta["Access-Control-Max-Age"] = "600"
    return resposta


def _cabecalhos(resposta, origem):
    patch_vary_headers(resposta, ("Origin",))
    if origem:
        resposta["Access-Control-Allow-Origin"] = origem
    return resposta


class AvaliacoesCorsMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        self.async_mode = iscoroutinefunction(get_response)
        if self.async_mode:
            markcoroutinefunction(self)

    def __call__(self, request):
        if self.async_mode:
            return self.__acall__(request)
        rota = ROTA.fullmatch(request.path_info)
        if rota is None:
            return self.get_response(request)
        request.get_host()  # A origem da loja nao substitui o Host publico do hub.
        origem = request.headers.get("Origin")
        if origem and not _origem_permitida(rota[1], origem):
            return _negada()
        if origem and request.method == "OPTIONS" and request.headers.get(
            "Access-Control-Request-Method"
        ):
            resposta = _preflight()
        else:
            resposta = self.get_response(request)
        return _cabecalhos(resposta, origem)

    async def __acall__(self, request):
        rota = ROTA.fullmatch(request.path_info)
        if rota is None:
            return await self.get_response(request)
        request.get_host()
        origem = request.headers.get("Origin")
        if origem and not await sync_to_async(_origem_permitida)(rota[1], origem):
            return _negada()
        if origem and request.method == "OPTIONS" and request.headers.get(
            "Access-Control-Request-Method"
        ):
            resposta = _preflight()
        else:
            resposta = await self.get_response(request)
        return _cabecalhos(resposta, origem)
