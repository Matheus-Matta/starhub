from celery import shared_task

from apps.core.tenant.context import tenant_context
from apps.starchats.cliente import ErroStarChats
from apps.starchats.models import ConfiguracaoStarChats
from apps.starchats.processamento import processar_evento
from apps.starchats.provedores import ErroProvedorMensagens
from apps.starchats.sincronizacao import sincronizar


@shared_task(autoretry_for=(ErroStarChats,), retry_backoff=True, max_retries=3)
def sincronizar_starchats(conta_id):
    with tenant_context(conta_id):
        configuracao = ConfiguracaoStarChats.objects.get()
        try:
            return sincronizar(configuracao)
        except Exception as erro:
            configuracao.ultimo_erro = str(erro)[:2000]
            configuracao.save(update_fields=["ultimo_erro", "updated_at"])
            raise


@shared_task(autoretry_for=(ErroProvedorMensagens,), retry_backoff=True, max_retries=3)
def enviar_evento_starchats(conta_id, tipo, objeto_id, evento, evento_id):
    with tenant_context(conta_id):
        return processar_evento(conta_id, tipo, objeto_id, evento, evento_id)
