"""Recebe o webhook de pedidos do Suri Shop.

Sem assinatura do lado do Suri: o endereco tem o uuid da configuracao (nao da para
adivinhar) e o pedido e relido pela API com o token (apps/suri/webhooks.py). O GET
responde 200: o Portal do Suri testa o endereco com um GET antes de salvar.
"""

import json

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from apps.core.tarefas import enfileirar
from apps.core.tenant.context import tenant_context
from apps.integracoes import trafego
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.suri.tasks import processar_webhook_suri
from apps.suri.webhooks import id_do_pedido


@csrf_exempt
def webhook(request, configuracao_uuid):
    configuracao = ConfiguracaoIntegracao.all_objects.filter(
        uuid=configuracao_uuid, plataforma=ConfiguracaoIntegracao.Plataforma.SURI,
        active=True).first()
    if configuracao is None:
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
    receber = (configuracao.habilitado("receber", "pedidos", "create")
               or configuracao.habilitado("receber", "pedidos", "update"))
    if not pedido_id or not receber:
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
