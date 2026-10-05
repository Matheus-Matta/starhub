"""Recebe os webhooks da loja WooCommerce.

A loja assina o corpo com HMAC-SHA256 (base64) usando o segredo do webhook, que o
cadastro do hub define como o segredo da chave da API (cs_). Ao cadastrar, o Woo manda
um "ping" (corpo de formulario `webhook_id=12`, sem topico): ele precisa de 200, senao
a loja recusa o webhook.
"""

import base64
import hashlib
import hmac
import json

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.tarefas import enfileirar
from apps.core.tenant.context import tenant_context
from apps.integracoes import trafego
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.woocommerce.tasks import processar_webhook_woocommerce
from apps.woocommerce.webhooks_cadastro import OPERACOES, TOPICOS

OPERACAO_DO_SUFIXO = {sufixo: operacao for operacao, sufixo in OPERACOES.items()}
# product.restored (saiu da lixeira) volta a valer como atualizacao.
OPERACAO_DO_SUFIXO["restored"] = "update"


def assinatura(segredo, corpo):
    return base64.b64encode(hmac.new(segredo.encode(), corpo, hashlib.sha256).digest()).decode()


def _assinatura_valida(configuracao, request):
    recebida = request.headers.get("X-WC-Webhook-Signature", "")
    segredo = configuracao.segredo_app
    return bool(recebida and segredo and
                hmac.compare_digest(assinatura(segredo, request.body), recebida))


def _operacao(recurso, topico):
    nome, _, sufixo = topico.partition(".")
    if TOPICOS.get(recurso) != nome:
        return None
    return OPERACAO_DO_SUFIXO.get(sufixo)


@csrf_exempt
@require_POST
def webhook(request, configuracao_uuid, recurso):
    configuracao = ConfiguracaoIntegracao.all_objects.filter(
        uuid=configuracao_uuid, plataforma=ConfiguracaoIntegracao.Plataforma.WOOCOMMERCE,
        active=True).first()
    if configuracao is None:
        return HttpResponse(status=404)
    topico = request.headers.get("X-WC-Webhook-Topic", "")
    if not topico and request.POST.get("webhook_id"):
        return HttpResponse(status=200)  # ping do cadastro: nao tem dado nem assinatura
    if not _assinatura_valida(configuracao, request):
        return HttpResponse(status=401)
    operacao = _operacao(recurso, topico)
    if operacao is None or not configuracao.habilitado("receber", recurso, operacao):
        return HttpResponse(status=204)
    try:
        dados = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"erro": "JSON invalido"}, status=400)
    with tenant_context(configuracao.account_id):
        execucao = ExecucaoIntegracao.objects.create(
            configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.RECEBER,
            etapa=f"Webhook {topico}",
            # O corpo fica guardado: sem ele o botao Retomar nao teria o que reprocessar.
            parametros={"reenvio": {"recurso": recurso, "operacao": operacao, "dados": dados},
                        # O corpo ja esta no reenvio; aqui so o resto, para a tela de Tarefas.
                        "requisicao": trafego.requisicao(request),
                        "resposta": trafego.resposta(202)},
        )
        resultado = enfileirar(processar_webhook_woocommerce, str(execucao.pk), recurso,
                               operacao, dados)
        ExecucaoIntegracao.objects.filter(pk=execucao.pk).update(celery_task_id=resultado.id)
    return HttpResponse(status=202)
