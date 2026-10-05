"""Pedido do Suri Shop (GET shop/orders/<id>) no pedido do hub.

    pedido, criado = importar_pedido(json_do_pedido_suri)

Status do Suri: 0 criando (carrinho, nao entra), 1 recebido, 2 pago, 3 cancelado,
4 erro. Logistica 4 (entregue) com pedido pago = concluido. O mesmo pedido chegando de
novo atualiza, nao duplica: quem segura dois webhooks juntos e o indice unico do
vinculo "pedidos".
"""

from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime

from apps.core.models import ExternalReference, Origin
from apps.loja.dinheiro import ZERO, texto
from apps.loja.models import PagamentoPedido, Pedido
from apps.loja.services.extras_pedido import mesclar_extras
from apps.loja.services.pedidos import gravar_endereco_do_pedido, gravar_transacao
from apps.loja.totais import recalcular_totais
from apps.suri import vinculos
from apps.suri.contexto import avisar
from apps.suri.importar_catalogo import valor
from apps.suri.importar_cliente import cliente_do_pedido, endereco
from apps.suri.importar_itens import gravar_itens

ORIGEM = Origin.SURI
CARRINHO, RECEBIDO, PAGO, CANCELADO, ERRO = range(5)
ENTREGUE = 4
STATUS = {RECEBIDO: Pedido.Status.PENDENTE, PAGO: Pedido.Status.PROCESSANDO,
          CANCELADO: Pedido.Status.CANCELADO, ERRO: Pedido.Status.FALHOU}
FINANCEIRO = {PAGO: "paid", CANCELADO: "voided", ERRO: "failed"}
# ShopPaymentMethod: a doc so nomeia estes dois; o resto fica como "suri_<numero>".
PAGAMENTOS = {0: ("credit_card", "Cartao de credito"), 3: ("pix", "Pix")}


class PedidoIgnorado(Exception):
    """Carrinho em andamento (status 0): ainda nao e pedido."""


def data(bruto):
    return parse_datetime(bruto) if bruto and not str(bruto).startswith("0001") else None


def _pedido_da_linha(dados):
    externo = str(dados["id"])
    obj = vinculos.existente("pedidos", Pedido, externo)
    if obj is not None:
        return obj, False
    try:
        with transaction.atomic():
            obj = Pedido.objects.create(external_number=str(dados.get("friendlyCode") or externo),
                                        source_name="suri", source_reference=externo,
                                        origin=ORIGEM)
            ExternalReference.objects.create(platform=ORIGEM, entity_type="pedidos",
                                             external_id=externo, object_id=str(obj.pk),
                                             origin=ORIGEM)
    except IntegrityError:
        return vinculos.existente("pedidos", Pedido, externo), False
    return obj, True


def _status(pedido, dados):
    situacao = dados.get("status")
    pedido.status = STATUS.get(situacao, pedido.status)
    pedido.financial_status = FINANCEIRO.get(situacao, "pending")
    logistica = (dados.get("logistic") or {}).get("status")
    if logistica == ENTREGUE and situacao == PAGO:
        pedido.status = Pedido.Status.CONCLUIDO
        pedido.fulfillment_status = Pedido.StatusEntrega.ATENDIDO
    metodo = (dados.get("payment") or {}).get("method")
    codigo, titulo = PAGAMENTOS.get(metodo, (f"suri_{metodo}", f"Suri ({metodo})"))
    pedido.forma_pagamento = codigo[:100] if metodo is not None else ""
    pedido.forma_pagamento_titulo = titulo[:200] if metodo is not None else ""
    pedido.placed_at = data(dados.get("createdDate")) or pedido.placed_at
    pedido.paid_at = (data(dados.get("finalizedDate")) or data(dados.get("receivedDate"))
                      if situacao == PAGO else pedido.paid_at)
    pedido.cancelled_at = data(dados.get("canceledDate"))


def _linhas(pedido, dados):
    entrega = dados.get("logistic") or {}
    frete = valor(entrega.get("price")) or ZERO
    pedido.linhas_frete = [{"id": 1, "method_id": str(entrega.get("providerId") or "")[:100],
                            "method_title": str(entrega.get("name") or ""),
                            "total": texto(frete), "total_tax": "0.00", "taxes": [],
                            "meta_data": []}] if entrega else []
    pedido.shipping_method = str(entrega.get("name") or "")[:150]
    taxas, taxa = [], valor(dados.get("feeAmount")) or ZERO
    if taxa:
        taxas.append({"id": 1, "name": "Taxa do Suri", "total": texto(taxa)})
    desconto = valor(dados.get("orderDiscountAmount")) or ZERO
    if desconto:
        # Desconto do pedido inteiro (nao de item): taxa negativa, como no Woo.
        taxas.append({"id": 2, "name": "Desconto do pedido", "total": texto(-desconto)})
    pedido.linhas_taxa = [{"tax_class": "", "tax_status": "none", "total_tax": "0.00",
                           "taxes": [], "meta_data": [], **t} for t in taxas]
    cupom = dados.get("coupon") or {}
    codigo = cupom.get("code") if isinstance(cupom, dict) else str(cupom)
    pedido.linhas_cupom = [{"id": 1, "code": codigo, "discount": "0.00", "discount_tax": "0.00",
                            "meta_data": []}] if codigo else []


def _conferir_total(pedido, dados):
    esperado = valor(dados.get("totalAmount"))
    if esperado is not None and esperado != pedido.total:
        avisar(f"Total do hub {pedido.total} difere do Suri {esperado}; confira o pedido.",
               recurso="pedidos", id=pedido.pk, descricao=pedido.number, id_externo=dados["id"])


@transaction.atomic
def importar_pedido(dados):
    if dados.get("status") in (None, CARRINHO):
        raise PedidoIgnorado("Carrinho em andamento no Suri (status 0): ainda nao e pedido.")
    pedido, criado = _pedido_da_linha(dados)
    # Lock e releitura: o que foi lido antes do lock pode ser de outro webhook.
    pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)
    comprador = dados.get("customer") or {}
    pedido.email = (comprador.get("email") or pedido.email)[:254]
    pedido.telefone = str(comprador.get("phone") or pedido.telefone)[:30]
    pedido.cliente = cliente_do_pedido(comprador) or pedido.cliente
    _status(pedido, dados)
    _linhas(pedido, dados)
    for tipo in ("billing", "shipping"):
        limpo = endereco(comprador)
        if limpo.get("address_1"):
            gravar_endereco_do_pedido(pedido, tipo, limpo)
    pedido.save()
    gravar_itens(pedido, dados)
    mesclar_extras(pedido, {"origem": {"canal": "suri", "id": str(dados["id"]),
                                       "usuario": dados.get("userId"),
                                       "loja": (dados.get("logistic") or {}).get("storeName")}})
    pedido.save(update_fields=["metadados", "updated_at"])
    recalcular_totais(pedido)
    _conferir_total(pedido, dados)
    pagamento = gravar_transacao(pedido, str((dados.get("payment") or {}).get("providerId")
                                             or dados["id"]))
    pagamento.amount, pagamento.currency = pedido.total, pedido.moeda
    pagamento.status = {"paid": PagamentoPedido.Status.PAGO,
                        "voided": PagamentoPedido.Status.ESTORNADO}.get(
        pedido.financial_status, PagamentoPedido.Status.PENDENTE)
    pagamento.save()
    # Estado do Suri no vinculo: o envio (envio/pedidos.py) so chama "pago", "cancelar"
    # ou a logistica quando o hub mudou algo que o Suri ainda nao tem.
    vinculos.referenciar("pedidos", dados["id"], pedido, metadata=estado_no_suri(dados))
    return pedido, criado


def estado_no_suri(dados):
    return {"pago": dados.get("status") == PAGO, "cancelado": dados.get("status") == CANCELADO,
            "logistica": (dados.get("logistic") or {}).get("status")}
