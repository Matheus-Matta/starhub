import base64
import hashlib
import hmac
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core.tarefas import enfileirar
from apps.core.tenant.context import tenant_context
from apps.integracoes import log_corpo, trafego
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.shopify.tasks import processar_webhook_shopify

OPERACOES_TOPICO = {
    "create": "create",
    "update": "update",
    "updated": "update",
    "delete": "delete",
}
logger = logging.getLogger("django.request")


def _registrar_recebido(request, configuracao, recurso):
    logger.info(
        "Shopify webhook recebido: configuracao=%s recurso=%s topico=%s loja=%s "
        "webhook_id=%s corpo=%s",
        configuracao.pk,
        recurso,
        request.headers.get("X-Shopify-Topic", ""),
        request.headers.get("X-Shopify-Shop-Domain", ""),
        request.headers.get("X-Shopify-Webhook-Id", ""),
        log_corpo.corpo(request.body),
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


def _motivo_da_rejeicao(configuracao, recebida):
    if not configuracao.segredo_app:
        return ("segredo do app vazio na configuracao: preencha o segredo do app "
                "(Shopify > Apps > Desenvolver apps > Credenciais da API)")
    if not recebida:
        return "requisicao sem X-Shopify-Hmac-Sha256: nao veio da Shopify"
    return ("HMAC diferente: o segredo do app no hub nao e o do app que cadastrou este "
            "webhook. Confira o segredo ou apague o webhook antigo na Shopify")


def _registrar_rejeicao(request, configuracao, recurso, recebida, calculada):
    # O motivo sai sempre: sem ele um 401 em prod nao diz se o segredo falta ou esta errado.
    detalhe = ""
    if log_corpo.ligado():
        detalhe = (f" hmac_recebido={recebida or '<ausente>'} "
                   f"hmac_calculado={calculada or '<segredo-ausente>'}")
    logger.warning(
        "Shopify webhook rejeitado (401): configuracao=%s (%s) recurso=%s topico=%s "
        "loja=%s dominio_configurado=%s corpo_bytes=%s corpo_sha256=%s motivo=%s%s",
        configuracao.pk,
        configuracao.nome,
        recurso,
        request.headers.get("X-Shopify-Topic", ""),
        request.headers.get("X-Shopify-Shop-Domain", ""),
        configuracao.dominio_loja or "-",
        len(request.body),
        hashlib.sha256(request.body).hexdigest(),
        _motivo_da_rejeicao(configuracao, recebida),
        detalhe,
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
        logger.warning("Shopify webhook para a configuracao %s inexistente ou desligada: "
                       "apague o webhook antigo na Shopify ou religue a integracao.",
                       configuracao_uuid or configuracao_id)
        return HttpResponse(status=404)
    recebida = request.headers.get("X-Shopify-Hmac-Sha256", "")
    calculada = _assinatura_calculada(configuracao, request.body)
    if not _assinatura_valida(recebida, calculada):
        _registrar_rejeicao(request, configuracao, recurso, recebida, calculada)
        return HttpResponse(status=401)
    _registrar_recebido(request, configuracao, recurso)
    topico = request.headers.get("X-Shopify-Topic", "")
    operacao = OPERACOES_TOPICO.get(topico.rsplit("/", 1)[-1])
    if operacao is None:
        logger.info("Shopify webhook ignorado (204): topico %s sem operacao conhecida.", topico)
        return HttpResponse(status=204)
    if not configuracao.habilitado("receber", recurso, operacao):
        logger.info("Shopify webhook ignorado (204): Receber > %s > %s desligado na "
                    "configuracao %s.", recurso, operacao, configuracao.pk)
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
