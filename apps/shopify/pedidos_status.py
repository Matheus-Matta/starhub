"""Pagamento e status do pedido do Shopify: gateway, status, datas e transacao."""

from apps.loja.models import PagamentoPedido, Pedido
from apps.loja.services.pedidos import gravar_transacao
from apps.shopify.pedidos_base import data

Status = Pedido.Status
_CANCELADOS = {"voided", "cancelled", "canceled"}
_PAGOS = {"paid", "partially_paid"}
# Pagamento na entrega: o Shopify deixa "pending", mas o pedido ja pode ser separado.
_NA_ENTREGA = ("cash on delivery", "cash_on_delivery", "(cod)", "pagamento na entrega")
_PAGAMENTO = {
    "paid": PagamentoPedido.Status.PAGO,
    "partially_refunded": PagamentoPedido.Status.PAGO,
    "authorized": PagamentoPedido.Status.AUTORIZADO,
    "refunded": PagamentoPedido.Status.REEMBOLSADO,
    "voided": PagamentoPedido.Status.ESTORNADO,
}


def gateway_do_pedido(dados):
    """O gateway mais recente e o ultimo de payment_gateway_names."""
    nomes = [nome for nome in dados.get("payment_gateway_names") or [] if nome]
    if nomes:
        return str(nomes[-1])
    termos = (dados.get("payment_terms") or {}).get("payment_terms_name")
    for candidato in (dados.get("gateway"), dados.get("payment_method"),
                      dados.get("payment_method_title"), termos):
        if candidato:
            return str(candidato)
    return ""


def _pago_em(dados):
    """Data da venda/captura aprovada; sem transacoes (o webhook nao traz), a do pedido."""
    for transacao in dados.get("transactions") or []:
        tipo = str(transacao.get("kind") or "").lower()
        situacao = str(transacao.get("status") or "").lower()
        if tipo in ("sale", "capture") and situacao == "success" and transacao.get("processed_at"):
            return data(transacao["processed_at"])
    return data(dados.get("processed_at") or dados.get("created_at"))


def _financeiro(dados):
    return str(dados.get("financial_status") or "").strip().lower()


def status_do_pedido(dados, gateway):
    financeiro = _financeiro(dados)
    if dados.get("cancelled_at"):
        return Status.CANCELADO
    if financeiro == "refunded":
        return Status.REEMBOLSADO
    if financeiro in _CANCELADOS:
        return Status.CANCELADO
    if any(trecho in gateway.casefold() for trecho in _NA_ENTREGA) or gateway.casefold() == "cod":
        return Status.PROCESSANDO
    if financeiro in _PAGOS:
        return Status.PROCESSANDO
    return Status.PENDENTE


def aplicar_status(pedido, dados):
    """Grava gateway, status e datas no pedido (sem salvar)."""
    gateway = gateway_do_pedido(dados)
    pedido.forma_pagamento_titulo = gateway[:200]
    pedido.forma_pagamento = gateway.removeprefix("appmax_")[:100]
    pedido.status = status_do_pedido(dados, gateway)
    financeiro = _financeiro(dados)
    if financeiro in Pedido.StatusFinanceiro.values:
        pedido.financial_status = financeiro
    entrega = str(dados.get("fulfillment_status") or "unfulfilled").lower()
    if entrega in Pedido.StatusEntrega.values:
        pedido.fulfillment_status = entrega
    if financeiro in _PAGOS and pedido.paid_at is None:
        pedido.paid_at = _pago_em(dados)
    pedido.cancelled_at = data(dados.get("cancelled_at"))


def gravar_pagamento(pedido, dados, numero):
    """Transacao com o id do pedido Shopify. Chame depois dos totais: o valor e o total."""
    pagamento = gravar_transacao(pedido, numero)
    pagamento.amount = pedido.total
    pagamento.currency = pedido.moeda
    pagamento.status = _PAGAMENTO.get(_financeiro(dados), PagamentoPedido.Status.PENDENTE)
    pagamento.paid_at = pedido.paid_at if pagamento.status == "paid" else pagamento.paid_at
    pagamento.save()
    return pagamento
