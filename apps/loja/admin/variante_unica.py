"""Produto simples (externo, agrupado) e bundle: a variante unica editada como
secoes da propria pagina do produto, sem lista nem modal.

Por baixo e um inline normal (1 formulario, a variante padrao); o template so
desenha os fieldsets dele como secoes (Identificacao, Imagens, Preco, Estoque,
Envio, Impostos). Produto variavel usa a lista de variantes (variantes.py).
"""

from apps.core.admin_base import TemaStackedInline
from apps.loja.admin.variantes import ENVIO, ESTOQUE, IMPOSTOS, PRECO, ConfigVariante
from apps.loja.models import VarianteProduto


class VarianteUnicaInline(ConfigVariante, TemaStackedInline):
    model = VarianteProduto
    fk_name = "produto"
    template = "admin/loja/variante_como_secoes.html"
    max_num = 1
    can_delete = False
    fieldsets = [
        ("Identificacao", {"fields": [("sku", "barcode")]}),
        ("Imagens", {"fields": ["imagens"]}),
        ("Preco", {"fields": PRECO}),
        # Bundle nao mostra: o estoque dele e calculado pelos componentes.
        ("Estoque", {"classes": ["secao-estoque"], "fields": ESTOQUE}),
        ("Envio", {"fields": ENVIO}),
        ("Impostos", {"fields": IMPOSTOS}),
    ]

    def get_queryset(self, request):
        # So a padrao: num produto variavel as outras aparecem na lista, nao aqui.
        return super().get_queryset(request).filter(is_default=True)

    def get_extra(self, request, obj=None, **kwargs):
        # Sem variante ainda: um formulario em branco (so e salvo se preenchido).
        tem = obj is not None and obj.variantes.filter(is_default=True).exists()
        return 0 if tem else 1
