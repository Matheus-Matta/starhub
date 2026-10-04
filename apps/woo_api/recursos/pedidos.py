from django.utils import timezone

from apps.loja.models import Cliente, Pedido
from apps.loja.services.pedidos import gravar_endereco_do_pedido, gravar_transacao
from apps.loja.totais import recalcular_totais
from apps.woo_api import datas
from apps.woo_api.erros import WooErro
from apps.woo_api.recursos import enderecos
from apps.woo_api.recursos.base import Recurso, booleano, escolha, inteiro, lista_de_ids, texto
from apps.woo_api.recursos.pedidos_linhas import gravar_itens, gravar_linhas
from apps.woo_api.recursos.pedidos_meta import gravar_meta, gravar_servicos
from apps.woo_api.recursos.pedidos_saida import pedido_para_woo
from apps.woo_api.recursos.termos import cadastrar_cupons

TEXTOS = {
    "payment_method": ("forma_pagamento", 100),
    "payment_method_title": ("forma_pagamento_titulo", 200),
    "customer_note": ("observacao_cliente", None),
    "customer_ip_address": ("ip_cliente", 64),
    "customer_user_agent": ("user_agent", 255),
    "created_via": ("source_name", 50),
    "currency": ("moeda", 3),
    "cart_hash": ("hash_carrinho", 64),
}
DATAS = (
    ("date_created", "placed_at"), ("date_paid", "paid_at"), ("date_completed", "fulfilled_at"),
)


def _cliente(valor):
    cliente_id = inteiro(valor or 0, "customer_id")
    if not cliente_id:
        return None
    cliente = Cliente.objects.filter(pk=cliente_id).first()
    if cliente is None:
        raise WooErro("woocommerce_rest_invalid_customer_id", "O ID do cliente e invalido.", 400)
    return cliente


def _aplicar_status(pedido, dados):
    agora = timezone.now()
    if booleano(dados.get("set_paid", False), "set_paid"):
        pedido.paid_at = pedido.paid_at or agora
        if pedido.status in ("pending", "on-hold", "failed"):
            pedido.status = Pedido.Status.PROCESSANDO
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


class PedidoRecurso(Recurso):
    modelo = Pedido
    nome = "shop_order"
    campo_busca = ("cliente__email", "cliente__nome", "pagamentos__transaction_id", "chave")
    campo_data = "placed_at"
    ordenacoes = {
        "id": "id", "include": "id", "date": "placed_at", "modified": "updated_at",
        "title": "id", "slug": "id",
    }

    def queryset(self):
        return Pedido.objects.select_related(
            "endereco_cobranca", "endereco_entrega"
        ).prefetch_related("itens__produto__midias__variante", "pagamentos")

    def filtrar(self, qs, params):
        status = [s.strip() for s in (params.get("status") or "any").split(",") if s.strip()]
        if status == ["any"]:
            qs = qs.exclude(status=Pedido.Status.LIXEIRA)
        else:
            for valor in status:
                escolha(valor, "status", Pedido.Status.values)
            qs = qs.filter(status__in=status)
        if params.get("customer") not in (None, ""):
            cliente = inteiro(params["customer"], "customer")
            qs = qs.filter(cliente_id=cliente or None)
        if params.get("product"):
            qs = qs.filter(itens__produto_id=inteiro(params["product"], "product"))
        if params.get("parent"):
            qs = qs.filter(id_pai__in=lista_de_ids(params, "parent"))
        # distinct: busca por transacao e filtro por produto passam por tabelas filhas.
        return super().filtrar(qs, params).distinct()

    def para_woo(self, obj):
        return pedido_para_woo(obj)

    def gravar(self, obj, dados, criando):
        for campo, (atributo, tamanho) in TEXTOS.items():
            if campo in dados:
                setattr(obj, atributo, texto(dados[campo], campo, tamanho))
        if "status" in dados:
            obj.status = escolha(dados["status"], "status", Pedido.Status.values)
        if "customer_id" in dados:
            obj.cliente = _cliente(dados["customer_id"])
        if "parent_id" in dados:
            obj.id_pai = inteiro(dados["parent_id"], "parent_id")
        if "prices_include_tax" in dados:
            obj.preco_inclui_imposto = booleano(dados["prices_include_tax"], "prices_include_tax")
        for tipo in ("billing", "shipping"):
            recebido = enderecos.recebido(dados, tipo)
            if recebido is not None:
                enderecos.gravar(gravar_endereco_do_pedido, obj, tipo, recebido, tipo=tipo)
        if "meta_data" in dados:
            gravar_meta(obj, dados["meta_data"])
        if "shipping_lines" in dados:
            obj.linhas_frete = gravar_linhas(obj.linhas_frete, dados, "shipping_lines", "method_id")
        if "fee_lines" in dados:
            obj.linhas_taxa = gravar_linhas(obj.linhas_taxa, dados, "fee_lines", "name")
        if "coupon_lines" in dados:
            # O desconto nao e recalculado aqui: ele precisa vir no total de cada item.
            obj.linhas_cupom = gravar_linhas(obj.linhas_cupom, dados, "coupon_lines", "code")
            cadastrar_cupons(dados["coupon_lines"])
        for prefixo, atributo in DATAS:
            if dados.get(prefixo) or dados.get(f"{prefixo}_gmt"):
                setattr(obj, atributo, datas.ler_do_corpo(dados, prefixo))
        if criando and obj.placed_at is None:
            obj.placed_at = timezone.now()
        _aplicar_status(obj, dados)
        obj.save()
        # Servicos depois dos itens: o campo starhub guarda o item_id de cada um.
        if "line_items" in dados and gravar_servicos(obj, gravar_itens(obj, dados)):
            obj.save(update_fields=["metadados", "updated_at"])
        recalcular_totais(obj)
        if "transaction_id" in dados:
            gravar_transacao(obj, texto(dados["transaction_id"], "transaction_id", 255))
        return obj
