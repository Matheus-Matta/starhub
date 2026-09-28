"""Enderecos e transacao de pagamento do pedido.

Pedido e documento historico: os enderecos dele sao copias proprias (snapshot),
nunca o endereco vivo do cliente.
"""

from apps.loja.models import PagamentoPedido
from apps.loja.services import enderecos
from apps.loja.services.clientes import endereco_do_cliente

CAMPOS_ENDERECO = {"billing": "endereco_cobranca", "shipping": "endereco_entrega"}
NOMES = {"billing": "Cobranca do pedido", "shipping": "Entrega do pedido"}


def gravar_endereco_do_pedido(pedido, tipo, dados, substituir=False):
    """Mescla `dados` (formato Woo) no snapshot do pedido. Salve o pedido depois."""
    campo = CAMPOS_ENDERECO[tipo]
    atual = getattr(pedido, campo)
    if atual is None:
        endereco = enderecos.snapshot(dados, NOMES[tipo], pedido.account_id)
    else:
        endereco = enderecos.aplicar(atual, dados, substituir)
        endereco.save()
    setattr(pedido, campo, endereco)
    return endereco


def copiar_enderecos_do_cliente(pedido):
    """Preenche o que faltar com uma COPIA do endereco atual do cliente."""
    if pedido.cliente_id is None:
        return
    for tipo, campo in CAMPOS_ENDERECO.items():
        if getattr(pedido, campo) is None:
            origem = endereco_do_cliente(pedido.cliente, tipo)
            setattr(pedido, campo, enderecos.clonar(origem, NOMES[tipo]))


def transacao(pedido):
    """transaction_id do Woo: o da primeira transacao registrada no pedido."""
    pagamento = next(iter(pedido.pagamentos.all()), None) if pedido.pk else None
    return pagamento.transaction_id if pagamento else ""


def gravar_transacao(pedido, transaction_id):
    """O Woo tem um transaction_id so; aqui ele e a primeira transacao do pedido."""
    pagamento = pedido.pagamentos.order_by("id").first()
    if pagamento is None:
        if not transaction_id:
            return None
        pagamento = PagamentoPedido(pedido=pedido, amount=pedido.total, currency=pedido.moeda)
    pagamento.provider = pedido.forma_pagamento or pagamento.provider or "desconhecido"
    pagamento.transaction_id = transaction_id
    pagamento.save()
    getattr(pedido, "_prefetched_objects_cache", {}).pop("pagamentos", None)
    return pagamento
