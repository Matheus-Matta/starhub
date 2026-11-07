"""Pedido -> JSON identico ao GET /wp-json/wc/v1/orders/<id> do WooCommerce."""

from apps.loja.dinheiro import ZERO
from apps.loja.dinheiro import texto as dinheiro_texto
from apps.loja.services.extras_pedido import somados_por_item
from apps.loja.services.pedidos import transacao
from apps.woo_api import datas
from apps.woo_api.recursos import enderecos
from apps.woo_api.recursos.pedidos_id import opcoes_da_conta
from apps.woo_api.recursos.pedidos_servicos import meta_do_item, servicos_por_item
from apps.woo_api.recursos.pedidos_starhub import meta_do_pedido

SIMBOLOS = {"BRL": "R$", "USD": "$", "EUR": "€"}


def item_para_woo(item, servicos=None, fora=ZERO):
    """`fora`: valor do servico somado no item que sai do subtotal/total da linha."""
    produto = item.produto
    imagens = produto.imagens if produto else []
    subtotal, total = item.subtotal - fora, item.total - fora
    return {
        "id": item.pk,
        "name": item.nome,
        "product_id": item.produto_id or 0,
        "variation_id": item.id_variacao,
        "quantity": item.quantidade,
        "tax_class": item.classe_fiscal,
        "subtotal": dinheiro_texto(subtotal),
        "subtotal_tax": dinheiro_texto(item.imposto_subtotal),
        "total": dinheiro_texto(total),
        "total_tax": dinheiro_texto(item.imposto_total),
        "taxes": item.impostos or [],
        "meta_data": meta_do_item(item, servicos),
        "sku": item.sku,
        # No Woo "price" e numero (nao texto): total da linha / quantidade.
        "price": float(total / item.quantidade if item.quantidade else total),
        "image": {"id": imagens[0].get("id", "") if imagens else "",
                  "src": imagens[0].get("src", "") if imagens else ""},
        "parent_name": None,
    }


def pedido_para_woo(pedido, servico_no_item=None, opcoes=None):
    """`servico_no_item`: o item sai como o hub guarda, com o servico somado. Vazio, vem
    do switch "servico no subtotal" da conta; desligado, o valor somado sai do item (ERP
    que soma o EPOFW contaria duas vezes). O total do pedido nao muda (o cliente pagou).
    `opcoes`: a listagem passa pronta, para nao consultar a conta a cada pedido."""
    if opcoes is None:
        opcoes = opcoes_da_conta(pedido.account_id)
    if servico_no_item is None:
        servico_no_item = opcoes.servico_no_subtotal
    id_api = pedido.pk + opcoes.base_id
    pago = pedido.status in ("processing", "completed")
    servicos = servicos_por_item(pedido)
    fora = {} if servico_no_item else somados_por_item(pedido)
    return {
        "id": id_api,
        "parent_id": pedido.id_pai,
        "status": pedido.status,
        "currency": pedido.moeda,
        "version": pedido.versao,
        "prices_include_tax": pedido.preco_inclui_imposto,
        **datas.par("date_created", pedido.placed_at or pedido.created_at),
        **datas.par("date_modified", pedido.updated_at),
        "discount_total": dinheiro_texto(pedido.total_desconto),
        "discount_tax": dinheiro_texto(pedido.imposto_desconto),
        "shipping_total": dinheiro_texto(pedido.total_frete),
        "shipping_tax": dinheiro_texto(pedido.imposto_frete),
        "cart_tax": dinheiro_texto(pedido.imposto_carrinho),
        "total": dinheiro_texto(pedido.total),
        "total_tax": dinheiro_texto(pedido.total_impostos),
        "customer_id": pedido.cliente_id or 0,
        "order_key": pedido.chave,
        "billing": enderecos.saida(pedido.endereco_cobranca, "billing", pedido.cliente),
        "shipping": enderecos.saida(pedido.endereco_entrega, "shipping"),
        "payment_method": pedido.forma_pagamento,
        "payment_method_title": pedido.forma_pagamento_titulo,
        "transaction_id": transacao(pedido),
        "customer_ip_address": pedido.ip_cliente,
        "customer_user_agent": pedido.user_agent,
        "created_via": pedido.source_name,
        "customer_note": pedido.observacao_cliente,
        **datas.par("date_completed", pedido.fulfilled_at),
        **datas.par("date_paid", pedido.paid_at),
        "cart_hash": pedido.hash_carrinho,
        "number": str(id_api),
        "meta_data": meta_do_pedido(pedido),
        "line_items": [item_para_woo(item, servicos.get(item.pk), fora.get(item.pk, ZERO))
                       for item in pedido.itens.all()],
        "tax_lines": pedido.linhas_imposto or [],
        "shipping_lines": pedido.linhas_frete or [],
        "fee_lines": pedido.linhas_taxa or [],
        "coupon_lines": pedido.linhas_cupom or [],
        "refunds": pedido.reembolsos or [],
        "payment_url": "",
        "is_editable": pedido.status in ("pending", "on-hold", "checkout-draft"),
        "needs_payment": not pago and pedido.status in ("pending", "failed"),
        "needs_processing": True,
        "currency_symbol": SIMBOLOS.get(pedido.moeda, pedido.moeda),
    }
