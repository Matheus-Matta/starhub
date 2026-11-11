"""Listas da pagina do pedido: itens (preco pela variante quando em branco),
pagamentos e entregas. Aparecem no formato de lista do tema (TemaTabularInline)."""

from django import forms

from apps.core.admin_base import TemaTabularInline
from apps.loja.dinheiro import ZERO, dinheiro
from apps.loja.models import EntregaPedido, ItemPedido, PagamentoPedido
from apps.loja.services.extras_pedido import somados_por_item
from apps.loja.totais import valores_do_item

# Preco do item ja gravado e o que o cliente pagou: mudar na tela desencontra o pedido
# da loja e do ERP.
PRECO_DO_ITEM = ["subtotal", "total"]


class ItemPedidoForm(forms.ModelForm):
    class Meta:
        model = ItemPedido
        fields = ["variante", "sku", "quantidade", "subtotal", "total"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Em branco = calcular pelo preco da variante (ver clean).
        self.fields["subtotal"].required = False
        self.fields["total"].required = False
        self.fields["variante"].label = "Produto"
        self.fields["sku"].disabled = True
        for nome in ("subtotal", "total"):
            self.fields[nome].widget.attrs["placeholder"] = "Automatico"
        if self.instance.pk:
            for nome in PRECO_DO_ITEM:
                self.fields[nome].disabled = True

    def clean(self):
        dados = super().clean()
        variante = dados.get("variante")
        produto = variante.produto if variante else None
        quantidade = dados.get("quantidade") or 0
        preco = variante.current_price if variante else None
        if self.instance.pk and "quantidade" in self.changed_data and self.instance.quantidade:
            dados["subtotal"], dados["total"] = self._pela_quantidade(quantidade)
        else:
            dados["subtotal"], dados["total"] = valores_do_item(
                preco, quantidade, dados.get("subtotal"), dados.get("total"))
        # Snapshot: nome e SKU ficam gravados no item mesmo se o produto mudar depois.
        if produto:
            dados["sku"] = variante.sku
        return dados

    def _pela_quantidade(self, quantidade):
        """Preco travado: vale o que o cliente pagou por unidade, nao o preco de hoje. O
        servico somado no item e um so (Montagem 80), entao fica fora da multiplicacao."""
        item = self.instance
        servico = somados_por_item(item.pedido).get(item.pk, ZERO)
        return tuple(dinheiro((valor - servico) * quantidade / item.quantidade + servico)
                     for valor in (item.subtotal, item.total))

    def save(self, commit=True):
        item = super().save(commit=False)
        variante = self.cleaned_data.get("variante")
        if variante:
            item.produto = variante.produto
            item.nome = variante.produto.nome
            item.sku = variante.sku
        if commit:
            item.save()
        return item


class ItemPedidoInline(TemaTabularInline):
    model = ItemPedido
    form = ItemPedidoForm
    extra = 0
    autocomplete_fields = ["variante"]
    relacao_so_adicionar = ["variante"]
    verbose_name, verbose_name_plural = "item", "itens do pedido"

    class Media:
        js = ["starhub/js/pedido-itens.js"]


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
