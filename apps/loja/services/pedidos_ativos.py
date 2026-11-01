"""Pedido desativado: fica so no hub, fora de toda integracao.

Desativado (active=False) o pedido nao vai a nenhum marketplace (distribuidor e
tarefa de envio), sai da lista da API Woo do ERP (pelo id responde e nao grava), nao e
alterado por webhook nem sincronizacao das lojas e nao dispara mensagem do
StarChats nem aviso. O registro e o historico ficam; reativar volta tudo ao normal.

    desativado(pedido)            # True se o pedido esta fora das integracoes
    mudar_ativo(pedido.pk, False) # True se mudou
"""

import logging

from django.db import transaction

from apps.loja.models import Pedido

AVISO_WEBHOOK = ("Pedido desativado no hub: webhook ignorado. Reative o pedido na lista "
                 "de pedidos para voltar a receber as alteracoes da loja.")

logger = logging.getLogger(__name__)


def desativado(obj):
    return isinstance(obj, Pedido) and not obj.active


def ignorar_entrada(pedido, canal):
    """True (e deixa rastro no log) quando a loja tenta alterar um pedido desativado."""
    if not desativado(pedido):
        return False
    logger.info("Pedido %s desativado: entrada de %s ignorada", pedido.pk, canal)
    return True


def mudar_ativo(pedido_id, ativo):
    """True se mudou. Sem envio as lojas nem na reativacao: o que o hub tem do pedido
    pode estar velho (os webhooks foram ignorados) e sobrescreveria a loja."""
    with transaction.atomic():
        # Relido depois do lock: um webhook ou outro lote pode ter mexido no meio.
        pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
        if pedido.active == ativo:
            return False
        pedido.active = ativo
        pedido._sem_envio = True
        pedido.save(update_fields=["active", "updated_at", "updated_by"])
    return True
