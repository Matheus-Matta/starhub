"""Recebe o webhook de pedidos do Suri Shop.

Sem assinatura do lado do Suri: o endereco tem o uuid da configuracao (nao da para
adivinhar) e o pedido e relido pela API com o token (apps/suri/webhooks.py). O GET
responde 200: o Portal do Suri testa o endereco com um GET antes de salvar.
"""

import json
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.core.tarefas import enfileirar
from apps.core.tenant.context import tenant_context
from apps.integracoes import log_corpo, trafego
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.suri.tasks import processar_webhook_suri
from apps.suri.webhooks import id_do_pedido

logger = logging.getLogger(__name__)


def _lojas_suri():
    return ConfiguracaoIntegracao.all_objects.filter(
        plataforma=ConfiguracaoIntegracao.Plataforma.SURI, active=True)


@csrf_exempt
def webhook_sem_uuid(request):
    """Endereco colado no Portal do Suri sem o uuid da loja (so a URL base).

    O Suri reenvia a cada poucos segundos enquanto recebe 404. Com uma loja Suri so,
    nao ha duvida de quem e: atende e avisa no log qual endereco cadastrar.
    """
    lojas = list(_lojas_suri().values_list("uuid", flat=True)[:2])
    if len(lojas) != 1:
        logger.warning("Webhook do Suri sem o uuid da loja e %s lojas Suri ativas: nao da "
                       "para saber de quem e. Cadastre no Portal do Suri o endereco da tela "
                       "da integracao (.../suri/webhook/<uuid>/). corpo=%s",
                       len(lojas) or "nenhuma", log_corpo.corpo(request.body))
        return HttpResponse(status=404)
    logger.warning("Webhook do Suri chegou em %s, sem o uuid; atendido pela unica loja Suri. "
                   "Troque no Portal do Suri para %s%s/.", request.path,
                   request.path.rstrip("/") + "/", lojas[0])
    return webhook(request, lojas[0])


@csrf_exempt
def webhook(request, configuracao_uuid):
    configuracao = _lojas_suri().filter(uuid=configuracao_uuid).first()
    if configuracao is None:
        logger.warning("Webhook do Suri para a loja %s inexistente ou desligada: confira o "
                       "endereco no Portal do Suri.", configuracao_uuid)
        return HttpResponse(status=404)
    if request.method == "GET":
        return HttpResponse("ok", content_type="text/plain")
    if request.method != "POST":
        return HttpResponse(status=405)
    try:
        corpo = json.loads(request.body or b"null")
    except (json.JSONDecodeError, UnicodeDecodeError):
        corpo = None
    pedido_id = id_do_pedido(corpo)
    evento = corpo.get("type", "") if isinstance(corpo, dict) else ""
    logger.info("Webhook do Suri recebido: loja=%s evento=%s pedido=%s corpo=%s",
                configuracao.pk, evento or "-", pedido_id or "-",
                log_corpo.corpo(request.body))
    receber = (configuracao.habilitado("receber", "pedidos", "create")
               or configuracao.habilitado("receber", "pedidos", "update"))
    if not pedido_id or not receber:
        logger.info("Webhook do Suri ignorado (204): %s",
                    "Receber > Pedidos desligado" if pedido_id else
                    f"sem id de pedido; chaves={json.dumps(log_corpo.estrutura(corpo))}")
        return HttpResponse(status=204)  # evento sem pedido (ou desligado): nada a fazer
    dados = {"id": pedido_id}
    with tenant_context(configuracao.account_id):
        execucao = ExecucaoIntegracao.objects.create(
            configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.RECEBER,
            etapa=f"Webhook pedido {pedido_id}",
            # So o id: o pedido e relido no Suri, entao o Retomar busca o estado atual.
            parametros={"reenvio": {"recurso": "pedidos", "operacao": "update", "dados": dados},
                        # O reenvio guarda so o id: o corpo inteiro fica aqui, para a tela.
                        "requisicao": trafego.requisicao(request, request.body),
                        "resposta": trafego.resposta(202)},
        )
        resultado = enfileirar(processar_webhook_suri, str(execucao.pk), "pedidos", "update",
                               dados)
        ExecucaoIntegracao.objects.filter(pk=execucao.pk).update(celery_task_id=resultado.id)
    return HttpResponse(status=202)
