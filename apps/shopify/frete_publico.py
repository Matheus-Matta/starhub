"""Consulta de frete para o calculador exibido no tema da loja Shopify.

O UUID evita enumerar lojas e o CORS limita navegadores. Origin nao autentica clientes
fora do navegador; a resposta contem somente as opcoes publicas de frete do checkout.
"""

from django.http import HttpResponse, JsonResponse
from django.utils.cache import patch_vary_headers

from apps.core.tenant.context import tenant_context
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.shopify.frete import opcoes_de_frete


def _com_cors(resposta, origem=None):
    patch_vary_headers(resposta, ("Origin",))
    if origem:
        resposta["Access-Control-Allow-Origin"] = origem
    resposta["Cache-Control"] = "no-store"
    return resposta


def _origem_permitida(configuracao, origem):
    permitidas = {f"https://{dominio}" for dominio in
                  configuracao.dominios_permitidos_no_frete()}
    return bool(origem) and origem.lower() in permitidas


def _negada():
    return _com_cors(JsonResponse({
        "erro": "origem_nao_permitida",
        "mensagem": "Dominio nao autorizado para consultar o frete.",
    }, status=403))


def consultar_frete(request, configuracao_uuid):
    """GET publico identificado por UUID; CORS limita o uso pelos navegadores."""
    configuracao = ConfiguracaoIntegracao.all_objects.select_related("account").filter(
        uuid=configuracao_uuid, plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY,
        active=True, account__active=True,
    ).first()
    if configuracao is None:
        return _com_cors(JsonResponse({"erro": "loja_nao_encontrada"}, status=404))
    request.get_host()
    origem = request.headers.get("Origin", "")
    if not _origem_permitida(configuracao, origem):
        return _negada()
    if request.method == "OPTIONS":
        resposta = HttpResponse(status=204)
        resposta["Access-Control-Allow-Methods"] = "GET"
        resposta["Access-Control-Max-Age"] = "600"
        return _com_cors(resposta, origem)
    if request.method != "GET":
        resposta = JsonResponse({"erro": "metodo_nao_permitido"}, status=405)
        resposta["Allow"] = "GET, OPTIONS"
        return _com_cors(resposta, origem)
    if not configuracao.frete_ativo:
        return _com_cors(JsonResponse({"rates": []}), origem)
    corpo = {"rate": {"destination": {
        "postal_code": request.GET.get("cep", ""),
        "city": request.GET.get("cidade", ""),
        "province": request.GET.get("uf", ""),
    }}}
    with tenant_context(configuracao.account_id):
        opcoes = opcoes_de_frete(
            corpo, exibir_prazo=configuracao.exibir_prazo_frete,
        )
    return _com_cors(JsonResponse({"rates": opcoes}), origem)
