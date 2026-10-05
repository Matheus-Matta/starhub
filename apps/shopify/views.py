import base64
import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.tarefas import enfileirar
from apps.core.tenant.context import tenant_context
from apps.integracoes import trafego
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.shopify.tasks import processar_webhook_shopify

OPERACOES_TOPICO = {
    "create": "create",
    "update": "update",
    "updated": "update",
    "delete": "delete",
}
logger = logging.getLogger("django.request")


def _registrar_webhook_em_dev(request, configuracao, recurso):
    if not settings.DEBUG:
        return
    try:
        corpo = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        corpo = request.body.decode(errors="replace")
    logger.info(
        "Shopify webhook recebido (DEV): configuracao=%s recurso=%s topico=%s "
        "loja=%s webhook_id=%s corpo=%s",
        configuracao.pk,
        recurso,
        request.headers.get("X-Shopify-Topic", ""),
        request.headers.get("X-Shopify-Shop-Domain", ""),
        request.headers.get("X-Shopify-Webhook-Id", ""),
        json.dumps(corpo, ensure_ascii=False, indent=2, default=str),
    )


def _assinatura_calculada(configuracao, corpo):
    segredo = configuracao.segredo_app
    if not segredo:
        return ""
    return base64.b64encode(
        hmac.new(segredo.encode(), corpo, hashlib.sha256).digest()
    ).decode()


def _assinatura_valida(recebida, calculada):
    return bool(recebida and calculada and hmac.compare_digest(calculada, recebida))


def _registrar_assinatura_em_dev(configuracao, recurso, corpo, recebida, calculada):
    if not settings.DEBUG:
        return
    logger.info(
        "Shopify HMAC (DEV): configuracao=%s recurso=%s status=%s "
        "hmac_recebido=%s hmac_calculado=%s corpo_bytes=%s corpo_sha256=%s",
        configuracao.pk,
        recurso,
        "valido" if _assinatura_valida(recebida, calculada) else "invalido",
        recebida or "<ausente>",
        calculada or "<segredo-ausente>",
        len(corpo),
        hashlib.sha256(corpo).hexdigest(),
    )


@csrf_exempt
@require_POST
def webhook(request, recurso, configuracao_uuid=None, configuracao_id=None):
    loja = {"uuid": configuracao_uuid} if configuracao_uuid else {"pk": configuracao_id}
    configuracao = ConfiguracaoIntegracao.all_objects.filter(
        **loja,
        plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY,
        active=True,
    ).first()
    if configuracao is None:
        return HttpResponse(status=404)
    _registrar_webhook_em_dev(request, configuracao, recurso)
    recebida = request.headers.get("X-Shopify-Hmac-Sha256", "")
    calculada = _assinatura_calculada(configuracao, request.body)
    assinatura_valida = _assinatura_valida(recebida, calculada)
    _registrar_assinatura_em_dev(
        configuracao, recurso, request.body, recebida, calculada
    )
    if not assinatura_valida:
        if settings.DEBUG:
            logger.warning(
                "Shopify webhook rejeitado (DEV): configuracao=%s recurso=%s "
                "motivo=assinatura HMAC invalida",
                configuracao.pk,
                recurso,
            )
        return HttpResponse(status=401)
    topico = request.headers.get("X-Shopify-Topic", "")
    operacao = OPERACOES_TOPICO.get(topico.rsplit("/", 1)[-1])
    if operacao is None:
        return HttpResponse(status=204)
    if not configuracao.habilitado("receber", recurso, operacao):
        return HttpResponse(status=204)
    try:
        dados = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON invalido"}, status=400)
    with tenant_context(configuracao.account_id):
        execucao = ExecucaoIntegracao.objects.create(
            configuracao=configuracao,
            tipo=ExecucaoIntegracao.Tipo.RECEBER,
            etapa=f"Webhook {topico}",
            # O corpo fica guardado: sem ele o botao Retomar nao teria o que reprocessar.
            parametros={"reenvio": {"recurso": recurso, "operacao": operacao, "dados": dados},
                        # O corpo ja esta no reenvio; aqui so o resto, para a tela de Tarefas.
                        "requisicao": trafego.requisicao(request),
                        "resposta": trafego.resposta(202)},
        )
        resultado = enfileirar(
            processar_webhook_shopify, str(execucao.pk), recurso, operacao, dados
        )
        ExecucaoIntegracao.objects.filter(pk=execucao.pk).update(celery_task_id=resultado.id)
    return HttpResponse(status=202)
