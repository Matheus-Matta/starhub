from django import forms
from django.contrib import admin
from django.db.models import Count
from django.template.loader import render_to_string

from apps.core.admin_base import TemaModelAdmin, TemaTabularInline
from apps.core.admin_utils import badge_status, iniciais_de, valor_moeda
from apps.core.filtros import FiltroPeriodo
from apps.loja.admin import campos
from apps.loja.admin.enderecos import EnderecosForm, secao_endereco
from apps.loja.models import EntregaPedido, ItemPedido, PagamentoPedido, Pedido
from apps.loja.services.pedidos import (
    CAMPOS_ENDERECO,
    copiar_enderecos_do_cliente,
    gravar_endereco_do_pedido,
)
from apps.loja.totais import recalcular_totais, valores_do_item


class ItemPedidoForm(forms.ModelForm):
    class Meta:
        model = ItemPedido
        fields = ["produto", "variante", "nome", "sku", "quantidade", "subtotal", "total"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Em branco = calcular pelo preco da variante (ver clean).
        self.fields["subtotal"].required = False
        self.fields["total"].required = False

    def clean(self):
        dados = super().clean()
        produto = dados.get("produto")
        variante = dados.get("variante") or (produto.variante_padrao if produto else None)
        dados["variante"] = variante
        quantidade = dados.get("quantidade") or 0
        preco = variante.current_price if variante else None
        dados["subtotal"], dados["total"] = valores_do_item(
            preco, quantidade, dados.get("subtotal"), dados.get("total")
        )
        # Snapshot: nome e SKU ficam gravados no item mesmo se o produto mudar depois.
        if produto:
            dados["nome"] = dados.get("nome") or produto.nome
            dados["sku"] = dados.get("sku") or (variante.sku if variante else "")
        return dados


class ItemPedidoInline(TemaTabularInline):
    model = ItemPedido
    form = ItemPedidoForm
    extra = 0
    autocomplete_fields = ["produto", "variante"]


class PagamentoInline(TemaTabularInline):
    model = PagamentoPedido
    extra = 0
    fields = ["provider", "transaction_id", "status", "amount", "installments", "paid_at"]


class EntregaInline(TemaTabularInline):
    model = EntregaPedido
    extra = 0
    fields = ["status", "tracking_company", "tracking_number", "tracking_url", "shipped_at",
              "delivered_at"]


class PedidoForm(EnderecosForm):
    class Meta:
        model = Pedido
        fields = "__all__"

    def endereco_inicial(self, tipo):
        return getattr(self.instance, CAMPOS_ENDERECO[tipo])


@admin.register(Pedido)
class PedidoAdmin(TemaModelAdmin):
    form = PedidoForm
    campos_json = campos.PEDIDO
    list_display = [
        "__str__", "created_at", "cliente_info", "total_fmt", "forma_pagamento_titulo",
        "itens_fmt", "status_badge",
    ]
    list_filter = [
        ("created_at", FiltroPeriodo), "status", "financial_status", "fulfillment_status",
        "forma_pagamento", "origin",
    ]
    search_fields = ["number", "external_number", "cliente__email", "cliente__nome",
                     "pagamentos__transaction_id", "chave"]
    list_select_related = ["cliente"]
    autocomplete_fields = ["cliente"]
    inlines = [ItemPedidoInline, PagamentoInline, EntregaInline]
    condicoes = {
        "cancelled_at": {"campo": "status", "em": ["cancelled"]},
        "paid_at": {"campo": "financial_status", "em": [
            "paid", "partially_paid", "refunded", "partially_refunded",
        ]},
        "fulfilled_at": [
            {"campo": "fulfillment_status", "em": ["fulfilled", "partial"]},
            {"campo": "status", "em": ["completed"]},
        ],
    }
    readonly_fields = [
        "chave", "total_desconto", "total_frete", "total_impostos", "total",
        "created_at", "updated_at",
    ]
    fieldsets = [
        ("Pedido", {"fields": [
            ("number", "external_number"), ("status", "moeda"),
            ("financial_status", "fulfillment_status"), "cliente", "observacao_cliente", "notas",
        ]}),
        ("Pagamento e entrega", {"fields": [
            ("forma_pagamento", "forma_pagamento_titulo"), ("placed_at", "paid_at"),
            ("fulfilled_at", "cancelled_at"), "shipping_method",
        ]}),
        ("Totais", {"fields": [("total_desconto", "total_frete"), ("total_impostos", "total")]}),
        secao_endereco("cobranca", "Endereco de cobranca", ["collapse"]),
        secao_endereco("entrega", "Endereco de entrega", ["collapse"]),
        ("Avancado", {"classes": ["collapse"], "fields": [
            "linhas_frete", "linhas_taxa", "linhas_cupom", "metadados",
            ("source_name", "source_reference"), "chave", ("created_at", "updated_at"),
        ]}),
    ]

    @admin.display(description="status", ordering="status")
    def status_badge(self, obj):
        return badge_status(obj.status, obj.get_status_display())

    @admin.display(description="total", ordering="total")
    def total_fmt(self, obj):
        return valor_moeda(obj.total)

    @admin.display(description="cliente", ordering="cliente__nome")
    def cliente_info(self, obj):
        cliente = obj.cliente
        nome = (cliente.nome_completo or cliente.email) if cliente else "Visitante"
        return render_to_string("components/table_cliente.html", {
            "avatar_url": cliente.avatar_url if cliente else "",
            "email": cliente.email if cliente else "Sem cadastro",
            "iniciais": iniciais_de(nome),
            "nome": nome,
        })

    @admin.display(description="itens", ordering="total_itens")
    def itens_fmt(self, obj):
        return f"{obj.total_itens} {'item' if obj.total_itens == 1 else 'itens'}"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(total_itens=Count("itens"))

    def save_model(self, request, obj, form, change):
        # Os enderecos sao FK: precisam existir antes de o pedido ser salvo.
        for tipo, dados in form.enderecos_alterados():
            gravar_endereco_do_pedido(obj, tipo, dados, substituir=True)
        if not change:
            copiar_enderecos_do_cliente(obj)
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Os itens so existem depois do inline salvo; so entao o total fecha.
        recalcular_totais(form.instance)
