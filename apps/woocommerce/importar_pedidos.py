"""Pedido da loja WooCommerce (GET orders ou webhook order.*) no pedido do hub.

    pedido, criado = importar_pedido(json_do_pedido_woo)

Os status do Woo sao os mesmos do hub (pending, processing, completed...). O pedido
chegando de novo (reenvio, order.updated) atualiza, nao duplica: quem segura dois
webhooks simultaneos e o indice unico do vinculo "pedidos".
"""

from datetime import UTC

from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime

from apps.core.models import ExternalReference, Origin
from apps.loja.models import Cliente, PagamentoPedido, Pedido
from apps.loja.services.extras_pedido import mesclar_extras
from apps.loja.services.pedidos import gravar_endereco_do_pedido, gravar_transacao
from apps.loja.totais import recalcular_totais
from apps.woocommerce import vinculos
from apps.woocommerce.importar_clientes import endereco, importar_cliente
from apps.woocommerce.importar_pedidos_itens import (
    gravar_itens,
    linhas_cupom,
    linhas_frete,
    linhas_taxa,
)

ORIGEM = Origin.WOOCOMMERCE
FINANCEIRO = {"processing": "paid", "completed": "paid", "refunded": "refunded",
              "failed": "failed", "cancelled": "voided"}
PAGAMENTO = {"paid": PagamentoPedido.Status.PAGO, "refunded": PagamentoPedido.Status.REEMBOLSADO,
             "voided": PagamentoPedido.Status.ESTORNADO}


def data(dados, campo):
    """O `_gmt` do Woo e UTC sem fuso: le ele e marca UTC (o sem _gmt e hora local da loja)."""
    bruto = dados.get(f"{campo}_gmt") or ""
    momento = parse_datetime(bruto) if bruto else None
    if momento is not None and momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento


def _pedido_da_linha(dados):
    externo = str(dados["id"])
    obj = vinculos.existente("pedidos", Pedido, externo)
    if obj is not None:
        return obj, False
    try:
        with transaction.atomic():
            obj = Pedido.objects.create(
                external_number=str(dados.get("number") or externo)[:100],
                source_name="woocommerce", source_reference=externo, origin=ORIGEM)
            ExternalReference.objects.create(platform=ORIGEM, entity_type="pedidos",
                                             external_id=externo, object_id=str(obj.pk),
                                             origin=ORIGEM)
    except IntegrityError:
        return vinculos.existente("pedidos", Pedido, externo), False
    return obj, True


def _cliente(dados):
    if dados.get("customer_id"):
        cliente = vinculos.existente("clientes", Cliente, dados["customer_id"])
        if cliente:
            return cliente
    cobranca = dados.get("billing") or {}
    obj, _ = importar_cliente({"id": dados.get("customer_id") or "", "email": cobranca.get(
        "email"), "billing": cobranca, "shipping": dados.get("shipping") or {}})
    return obj


def _campos(pedido, dados):
    cobranca = dados.get("billing") or {}
    pedido.external_number = str(dados.get("number") or dados["id"])[:100]
    if dados.get("status") in Pedido.Status.values:
        pedido.status = dados["status"]
    financeiro = FINANCEIRO.get(dados.get("status"), "pending")
    pedido.financial_status = financeiro
    pedido.moeda = (dados.get("currency") or pedido.moeda)[:3]
    pedido.email = (cobranca.get("email") or pedido.email)[:254]
    pedido.telefone = str(cobranca.get("phone") or pedido.telefone)[:30]
    pedido.observacao_cliente = dados.get("customer_note") or ""
    pedido.preco_inclui_imposto = bool(dados.get("prices_include_tax"))
    pedido.forma_pagamento = str(dados.get("payment_method") or "")[:100]
    pedido.forma_pagamento_titulo = str(dados.get("payment_method_title") or "")[:200]
    pedido.placed_at = data(dados, "date_created") or pedido.placed_at
    pedido.paid_at = data(dados, "date_paid") or pedido.paid_at
    pedido.fulfilled_at = data(dados, "date_completed") or pedido.fulfilled_at
    if dados.get("status") == "completed":
        pedido.fulfillment_status = Pedido.StatusEntrega.ATENDIDO
    pedido.ip_cliente = str(dados.get("customer_ip_address") or "")[:64]
    pedido.user_agent = str(dados.get("customer_user_agent") or "")[:255]
    pedido.source_name, pedido.source_reference = "woocommerce", str(dados["id"])
    pedido.linhas_frete = linhas_frete(dados)
    pedido.linhas_taxa = linhas_taxa(dados)
    pedido.linhas_cupom = linhas_cupom(dados)
    frete = dados.get("shipping_lines") or []
    pedido.shipping_method = str(frete[0].get("method_title") or "")[:150] if frete else ""
    pedido.cliente = _cliente(dados) or pedido.cliente


def _pagamento(pedido, dados):
    pagamento = gravar_transacao(pedido, str(dados.get("transaction_id") or dados["id"]))
    pagamento.amount, pagamento.currency = pedido.total, pedido.moeda
    pagamento.status = PAGAMENTO.get(pedido.financial_status, PagamentoPedido.Status.PENDENTE)
    pagamento.paid_at = pedido.paid_at if pagamento.status == "paid" else pagamento.paid_at
    pagamento.save()


@transaction.atomic
def importar_pedido(dados, loja=""):
    """`loja`: endereco da loja para o link do pedido no wp-admin."""
    pedido, criado = _pedido_da_linha(dados)
    # Lock e releitura: o que foi lido antes do lock pode ser de outro webhook.
    pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)
    _campos(pedido, dados)
    for tipo in ("billing", "shipping"):
        limpo = endereco(dados.get(tipo))
        if limpo:
            gravar_endereco_do_pedido(pedido, tipo, limpo)
    pedido.save()
    gravar_itens(pedido, dados)
    url = f"{loja.rstrip('/')}/wp-admin/post.php?post={dados['id']}&action=edit" if loja else ""
    mesclar_extras(pedido, {"origem": {"canal": "woocommerce", "id": str(dados["id"]),
                                       "numero": str(dados.get("number") or ""), "url": url,
                                       "atualizado_em": dados.get("date_modified_gmt")}})
    pedido.save(update_fields=["metadados", "updated_at"])
    recalcular_totais(pedido)
    _pagamento(pedido, dados)
    return pedido, criado
