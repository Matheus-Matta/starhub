"""Acoes "Mudar status para ..." na lista de pedidos (uma por status)."""

from django.contrib import admin, messages

from apps.loja.models import Pedido
from apps.loja.services.pedidos_status import mudar_status

# Rascunho e o carrinho do checkout do Woo: o operador nunca volta um pedido para la.
FORA_DO_LOTE = {Pedido.Status.RASCUNHO}


def mudar_em_lote(request, queryset, status):
    # Um por um e em ordem de id: o lock de cada linha nao cruza com outro lote.
    ids = list(queryset.order_by("pk").values_list("pk", flat=True))
    mudaram = sum(mudar_status(pk, status) for pk in ids)
    iguais = len(ids) - mudaram
    rotulo = Pedido.Status(status).label
    if mudaram:
        extra = f" ({iguais} ja estava(m) assim)" if iguais else ""
        messages.success(request, f"{mudaram} pedido(s) agora com status {rotulo}.{extra}")
    else:
        messages.warning(request, f"Nenhum pedido mudou: todos ja estavam {rotulo}.")


def _acao(status):
    def acao(modeladmin, request, queryset):
        mudar_em_lote(request, queryset, status)

    acao.__name__ = f"status_{status.value.replace('-', '_')}"
    return admin.action(description=f"Mudar status para {status.label}",
                        permissions=["change"])(acao)


ACOES_STATUS = [_acao(status) for status in Pedido.Status if status not in FORA_DO_LOTE]
