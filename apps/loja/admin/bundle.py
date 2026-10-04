"""Bundle: lista de componentes (produtos juntados no kit) e o estoque calculado.

O bundle nao tem estoque proprio: o componente que acaba primeiro manda
(Produto.estoque_do_bundle). Kit = 1 mouse + 2 pilhas; 10 mouses e 6 pilhas = 3.
"""

from django.contrib import admin
from django.utils.html import format_html

from apps.core.admin_base import TemaTabularInline
from apps.loja.models import ItemBundle


class ComponenteInline(TemaTabularInline):
    model = ItemBundle
    fk_name = "bundle_product"
    extra = 0
    fields = ["component_variant", "quantity", "estoque_componente"]
    readonly_fields = ["estoque_componente"]
    autocomplete_fields = ["component_variant"]
    relacao_so_adicionar = ["component_variant"]
    verbose_name = "componente"
    verbose_name_plural = "componentes do bundle"

    @admin.display(description="estoque do componente")
    def estoque_componente(self, obj):
        variante = obj.component_variant if obj.pk else None
        if variante is None:
            return "-"
        if not variante.manage_inventory:
            return "sem controle"
        return variante.inventory_quantity


def estoque_calculado(produto):
    """Texto da secao "Estoque" do bundle: quanto ha e quem limita."""
    if produto.pk is None:
        return "Calculado pelos componentes depois de salvar."
    quantidade, limitante = produto.estoque_do_bundle()
    if limitante is None:
        if not produto.componentes.exists():
            return "Sem componentes: adicione os produtos do kit para calcular o estoque."
        return "Sem limite: nenhum componente controla estoque."
    return format_html(
        "<strong>{} unidade(s)</strong> &mdash; limitado por {} ({} em estoque).",
        quantidade, limitante, limitante.inventory_quantity,
    )
