"""Rota que a Shopify chama no checkout para cotar o frete (CarrierService).

    POST /integracoes/shopify/frete/<uuid da configuracao>/
    -> 200 {"rates": [...]}    (lista vazia = nenhuma tabela atende o CEP ou frete desligado)
    -> 404 loja desconhecida | 400 corpo que nao e JSON

A Shopify nao assina requisicoes de CarrierService como assina webhooks. O UUID aleatorio
da configuracao identifica a loja sem expor seu id sequencial. Responder rapido importa
mais que tudo: a Shopify desiste em 3 s e o cliente fica sem opcao de frete.
"""

import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.tenant.context import tenant_context
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.shopify.frete import cep_de_destino, opcoes_de_frete

logger = logging.getLogger("django.request")


@csrf_exempt
@require_POST
def cotar_frete(request, configuracao_uuid):
    configuracao = ConfiguracaoIntegracao.all_objects.filter(
        uuid=configuracao_uuid, plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY,
        active=True,
    ).first()
    if configuracao is None:
        return HttpResponse(status=404)
    if not configuracao.frete_ativo:
        # Desligado no hub: nem calcula. A Shopify ainda pode chamar ate a tarefa marcar o
        # cadastro como inativo la.
        return JsonResponse({"rates": []})
    try:
        corpo = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON invalido"}, status=400)
    with tenant_context(configuracao.account_id):
        opcoes = opcoes_de_frete(corpo)
    logger.info("Frete cotado para o CEP %s: %s opcao(oes)", cep_de_destino(corpo), len(opcoes))
    return JsonResponse({"rates": opcoes})
