"""Demo de pedidos: itens, pagamento, entrega e copia dos enderecos do cliente.

Cada pedido cai numa situacao diferente (concluido, em transito, cancelado,
reembolsado...), com os status financeiro e de entrega coerentes com ela.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.loja.demo import marca
from apps.loja.dinheiro import dinheiro, somar
from apps.loja.models import EntregaPedido, ItemPedido, PagamentoPedido, Pedido
from apps.loja.services.pedidos import copiar_enderecos_do_cliente

# (status, financeiro, entrega, pagamento, situacao da entrega)
SITUACOES = [
    ("completed", "paid", "fulfilled", "paid", "delivered"),
    ("processing", "paid", "partial", "paid", "in_transit"),
    ("pending", "pending", "unfulfilled", "pending", None),
    ("on-hold", "authorized", "unfulfilled", "authorized", None),
    ("cancelled", "voided", "unfulfilled", "voided", None),
    ("refunded", "refunded", "returned", "refunded", "returned"),
    ("completed", "paid", "fulfilled", "paid", "delivered"),
    ("processing", "paid", "unfulfilled", "paid", None),
    ("completed", "paid", "fulfilled", "paid", "delivered"),
    ("failed", "failed", "unfulfilled", "failed", None),
]
FORMAS = [("pix", "Pix"), ("credit_card", "Cartao de credito"), ("boleto", "Boleto")]
FRETE = Decimal("19.90")
# De onde o pedido veio: mostra o badge de origem de cada plataforma na listagem.
ORIGENS = ["shopify", "woocommerce", "mercado_livre", "shopee", "amazon", "magalu", "starhub",
           "api"]


def _itens(pedido, variantes, i):
    itens = []
    for n in range(1 + i % 3):
        variante = variantes[(i * 3 + n) % len(variantes)]
        quantidade = 1 + (i + n) % 2
        preco = dinheiro(variante.current_price or 0)
        subtotal = dinheiro(preco * quantidade)
        itens.append(ItemPedido.objects.create(
            pedido=pedido, variante=variante, quantidade=quantidade, preco_unitario=preco,
            subtotal=subtotal, total=subtotal, peso=variante.weight, metadados=marca(),
        ))
    return itens


def pedidos(clientes, variantes, quantidade):
    agora = timezone.now()
    for i in range(quantidade):
        status, financeiro, entrega, pagamento, envio = SITUACOES[i % len(SITUACOES)]
        cliente = clientes[i % len(clientes)]
        forma, titulo = FORMAS[i % len(FORMAS)]
        feito_em = agora - timedelta(days=i * 3, hours=i)
        pedido = Pedido.objects.create(
            status=status, financial_status=financeiro, fulfillment_status=entrega, moeda="BRL",
            cliente=cliente, email=cliente.email, telefone=cliente.telefone,
            placed_at=feito_em, forma_pagamento=forma, forma_pagamento_titulo=titulo,
            shipping_method="Correios SEDEX", source_name="demo",
            external_number=f"DEMO-{i + 1:04d}",
            observacao_cliente="Entregar em horario comercial." if i % 4 == 0 else "",
            origin=ORIGENS[i % len(ORIGENS)], metadados=marca(),
        )
        subtotal = somar(item.subtotal for item in _itens(pedido, variantes, i))
        desconto = dinheiro(subtotal * Decimal("0.10")) if i % 3 == 0 else Decimal("0.00")
        frete = Decimal("0.00") if subtotal >= 300 else FRETE
        pedido.subtotal, pedido.total_desconto, pedido.total_frete = subtotal, desconto, frete
        pedido.total = subtotal - desconto + frete
        pago = financeiro in ("paid", "refunded")
        pedido.paid_at = feito_em + timedelta(minutes=30) if pago else None
        pedido.cancelled_at = feito_em + timedelta(days=1) if status == "cancelled" else None
        pedido.fulfilled_at = feito_em + timedelta(days=4) if entrega == "fulfilled" else None
        pedido.total_reembolsado = pedido.total if status == "refunded" else Decimal("0.00")
        copiar_enderecos_do_cliente(pedido)
        pedido.save()
        for campo in ("endereco_entrega", "endereco_cobranca"):
            endereco = getattr(pedido, campo)
            if endereco is not None:
                endereco.metadados = marca()
                endereco.save()
        PagamentoPedido.objects.create(
            pedido=pedido, provider=forma, transaction_id=f"demo-tx-{i + 1:05d}", status=pagamento,
            amount=pedido.total, currency="BRL", installments=3 if forma == "credit_card" else 1,
            paid_at=pedido.paid_at, metadados=marca(),
        )
        if envio:
            EntregaPedido.objects.create(
                pedido=pedido, status=envio, tracking_company="Correios",
                tracking_number=f"DM{i + 1:09d}BR",
                tracking_url=f"https://rastreamento.example.com/DM{i + 1:09d}BR",
                shipped_at=feito_em + timedelta(days=1),
                delivered_at=pedido.fulfilled_at if envio == "delivered" else None,
                metadados=marca(),
            )
