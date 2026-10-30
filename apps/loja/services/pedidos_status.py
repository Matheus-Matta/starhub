"""Mudanca de status do pedido com as datas que o Woo marca junto.

A API (apps/woo_api/recursos/pedidos.py) e a acao em lote do admin usam a mesma
regra: o ERP le date_paid e date_completed, e status sem a data vira buraco no ERP.
"""

from django.db import transaction
from django.utils import timezone

from apps.loja.models import Cliente, Pedido


def aplicar_datas_do_status(pedido):
    agora = timezone.now()
    # Igual ao Woo: chegar em processando/concluido marca a data de pagamento.
    if pedido.status in Pedido.PAGOS:
        pedido.paid_at = pedido.paid_at or agora
        pedido.financial_status = Pedido.StatusFinanceiro.PAGO
        if pedido.cliente_id:
            Cliente.objects.filter(pk=pedido.cliente_id).update(cliente_pagante=True)
    if pedido.status == Pedido.Status.CONCLUIDO:
        pedido.fulfilled_at = pedido.fulfilled_at or agora
        pedido.fulfillment_status = Pedido.StatusEntrega.ATENDIDO
    if pedido.status == Pedido.Status.CANCELADO:
        pedido.cancelled_at = pedido.cancelled_at or agora


def mudar_status(pedido_id, status):
    """True se mudou. save() (e nao update()): o post_save avisa StarChats e as lojas."""
    with transaction.atomic():
        # Relido depois do lock: um webhook pode ter mudado o pedido no meio do lote.
        pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
        if pedido.status == status:
            return False
        pedido.status = status
        aplicar_datas_do_status(pedido)
        pedido.save()
    return True
