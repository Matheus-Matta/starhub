"""Servicos do produto para o bloco do tema Shopify (Guia dos servicos).

    GET /integracoes/shopify/servicos-publico/<uuid>/?produto=<product.id do Liquid>
    -> {"servicos": [{"id": 3, "nome": "Montagem", "preco": "80.00",
                      "preco_texto": "R$ 80,00", "variante": 4455667788}]}

`variante` e a variante do produto escondido do servico com o preco que vale para
este produto (servicos_envio.py): e ela que o tema poe no carrinho. Mesmo controle do
frete do tema (frete_publico.py): UUID na URL e CORS so para os dominios da loja.
Desligado na tela, ou servico ainda nao exportado, a lista vem vazia.
"""

from django.http import HttpResponse, JsonResponse

from apps.core.models import ExternalReference
from apps.core.tenant.context import tenant_context
from apps.core.ui.formatos import moeda
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Produto
from apps.shopify.envio.produtos_variantes import dinheiro
from apps.shopify.frete_publico import _com_cors, _negada, _origem_permitida
from apps.shopify.servicos_envio import VARIANTES


def _produto(produto_id):
    if not str(produto_id or "").isdigit():
        return None
    referencia = ExternalReference.objects.filter(
        platform="shopify", entity_type="produtos",
        external_id=f"gid://shopify/Product/{produto_id}").first()
    return Produto.objects.filter(pk=referencia.object_id).first() if referencia else None


def _variantes(servicos):
    """{(servico_id, "80.00"): id numerico da variante} das variantes ja exportadas."""
    referencias = ExternalReference.objects.filter(
        platform="shopify", entity_type=VARIANTES,
        object_id__in=[str(servico.pk) for servico, _ in servicos])
    return {(int(r.object_id), (r.metadata or {}).get("preco")): r.external_id.rsplit("/", 1)[-1]
            for r in referencias}


def servicos_da_pagina(produto_id):
    produto = _produto(produto_id)
    servicos = produto.servicos if produto else []
    variantes = _variantes(servicos)
    saida = []
    for servico, preco in servicos:
        variante = variantes.get((servico.pk, dinheiro(preco)))
        if variante and variante.isdigit():
            saida.append({"id": servico.pk, "nome": servico.nome, "preco": dinheiro(preco),
                          "preco_texto": moeda(preco), "variante": int(variante)})
    return saida


def consultar_servicos(request, configuracao_uuid):
    configuracao = ConfiguracaoIntegracao.all_objects.select_related("account").filter(
        uuid=configuracao_uuid, plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY,
        active=True, account__active=True).first()
    if configuracao is None:
        return _com_cors(JsonResponse({"erro": "loja_nao_encontrada"}, status=404))
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
    if not configuracao.servicos_no_tema:
        return _com_cors(JsonResponse({"servicos": []}), origem)
    with tenant_context(configuracao.account_id):
        servicos = servicos_da_pagina(request.GET.get("produto"))
    return _com_cors(JsonResponse({"servicos": servicos}), origem)
