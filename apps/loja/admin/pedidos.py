from django.contrib import admin
from django.db.models import Count
from django.template.loader import render_to_string
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.timezone import localtime

from apps.core.admin_base import TemaModelAdmin
from apps.core.admin_utils import (
    badge,
    badge_origem,
    badge_status,
    iniciais_de,
    na_listagem,
    valor_moeda,
)
from apps.core.filtros import FiltroPeriodo
from apps.loja.admin import campos
from apps.loja.admin.codigo_externo import SEM_CODIGO
from apps.loja.admin.detalhes import itens_do_pedido
from apps.loja.admin.enderecos import EnderecosForm, secao_endereco
from apps.loja.admin.pedidos_inlines import EntregaInline, ItemPedidoInline, PagamentoInline
from apps.loja.models import Pedido
from apps.loja.services.pedidos import (
    CAMPOS_ENDERECO,
    copiar_enderecos_do_cliente,
    gravar_endereco_do_pedido,
)
from apps.loja.totais import recalcular_totais

# So classes de badge que o tema ja tem (componentes.css); estados nao listados caem em "secondary".
TONS_PAGAMENTO = {
    "paid": "success",
    "pending": "warning",
    "authorized": "warning",
    "partially_paid": "warning",
    "refunded": "info",
    "partially_refunded": "info",
    "voided": "destructive",
    "failed": "destructive",
}


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
        "numero", "codigo_externo", "criado_em", "cliente_info", "total_fmt", "pagamento",
        "itens_fmt", "status_badge", "origem_badge", "acoes",
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

    @admin.display(description="pedido", ordering="number")
    def numero(self, obj):
        return f"#{obj.number}"

    @admin.display(description="numero externo", ordering="external_number")
    def codigo_externo(self, obj):
        return format_html('<span class="nowrap">{}</span>', obj.external_number or SEM_CODIGO)

    @admin.display(description="criado em", ordering="created_at")
    def criado_em(self, obj):
        # Data curta: por extenso ("29 de Setembro de 2026 as 03:50") empurrava
        # origem e acoes para fora da tela.
        return date_format(localtime(obj.created_at), "d/m/Y H:i")

    @admin.display(description="pagamento", ordering="financial_status")
    def pagamento(self, obj):
        # A forma de pagamento continua no filtro lateral e no formulario.
        tom = TONS_PAGAMENTO.get(obj.financial_status, "secondary")
        return badge(obj.get_financial_status_display(), tom)

    @admin.display(description="origem", ordering="origin")
    def origem_badge(self, obj):
        return badge_origem(obj.origin, obj.get_origin_display())

    @admin.display(description="acoes")
    def acoes(self, obj):
        return itens_do_pedido(obj)

    def get_queryset(self, request):
        pedidos = super().get_queryset(request).annotate(total_itens=Count("itens"))
        if na_listagem(request):  # itens com imagem para a coluna "Acoes"
            pedidos = pedidos.prefetch_related("itens__variante__midias", "itens__produto__midias")
        return pedidos

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
