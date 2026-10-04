"""Listas da pagina do pedido: itens (preco pela variante quando em branco),
pagamentos e entregas. Aparecem no formato de lista do tema (TemaTabularInline)."""

from django import forms

from apps.core.admin_base import TemaTabularInline
from apps.loja.models import EntregaPedido, ItemPedido, PagamentoPedido
from apps.loja.totais import valores_do_item


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
    relacao_so_adicionar = ["produto", "variante"]
    verbose_name, verbose_name_plural = "item", "itens do pedido"


class PagamentoInline(TemaTabularInline):
    model = PagamentoPedido
    extra = 0
    verbose_name, verbose_name_plural = "pagamento", "pagamentos"
    fields = ["provider", "transaction_id", "status", "amount", "installments", "paid_at"]


class EntregaInline(TemaTabularInline):
    model = EntregaPedido
    extra = 0
    verbose_name, verbose_name_plural = "entrega", "entregas"
    fields = ["status", "tracking_company", "tracking_number", "tracking_url", "shipped_at",
              "delivered_at"]
