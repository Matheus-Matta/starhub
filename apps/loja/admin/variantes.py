"""Variante do produto: a lista na pagina do produto e o formulario do modal.

Na pagina do produto as variantes aparecem numa lista (lista_variantes); clicar
numa linha, em "Editar" ou em "Adicionar variante" abre o VarianteProdutoAdmin
num modal (_popup), com os campos, regras e widgets definidos aqui.
"""

from django import forms
from django.contrib import admin
from django.template.loader import render_to_string

from apps.core.admin_base import TemaModelAdmin
from apps.core.admin_lista_modal import url_popup
from apps.core.json_widgets import CampoJSON, ImagensTema
from apps.loja.admin import campos
from apps.loja.admin.opcoes import OpcoesInline
from apps.loja.models import VarianteProduto
from apps.loja.services.midias import imagens_da_variante, sincronizar_midias

PRECO = [("price", "sale_price"), ("compare_at_price", "cost"), ("sale_starts_at", "sale_ends_at")]
ESTOQUE = [
    ("manage_inventory", "inventory_quantity"), ("inventory_policy", "stock_status"),
    ("low_stock_amount", "sold_individually"),
]
ENVIO = [("requires_shipping", "shipping_class"), ("weight", "weight_unit"), "dimensions"]
IMPOSTOS = [("taxable", "tax_class")]


class VarianteForm(forms.ModelForm):
    """Galeria da variante: arrastar para ordenar; a primeira e a capa."""

    imagens = CampoJSON(
        widget=ImagensTema(pasta="produtos"), required=False, label="Imagens",
        help_text="Arraste para ordenar. A primeira e a principal (capa).",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault("imagens", imagens_da_variante(self.instance))
        if "titulo" in self.fields:
            # Em branco = montado das opcoes ("Branco / 42") ao salvar.
            self.fields["titulo"].required = False
            self.fields["titulo"].widget.attrs["placeholder"] = "Em branco: pelas opcoes"

    def _save_m2m(self):
        # Roda depois de a variante existir, no save() do inline e no do ModelAdmin.
        super()._save_m2m()
        if "imagens" in self.changed_data:
            sincronizar_midias(self.instance, self.cleaned_data.get("imagens") or [])


class ConfigVariante:
    form = VarianteForm
    campos_json = campos.VARIANTE
    periodos = [("sale_starts_at", "sale_ends_at")]
    condicoes = {
        # Com o estoque controlado a situacao e calculada; sem controle, escolhe-se a mao.
        "inventory_quantity": {"campo": "manage_inventory", "marcado": True},
        "inventory_policy": {"campo": "manage_inventory", "marcado": True},
        "low_stock_amount": {"campo": "manage_inventory", "marcado": True},
        "stock_status": {"campo": "manage_inventory", "marcado": False},
        "weight": {"campo": "requires_shipping", "marcado": True},
        "weight_unit": {"campo": "requires_shipping", "marcado": True},
        "dimensions": {"campo": "requires_shipping", "marcado": True},
        "shipping_class": {"campo": "requires_shipping", "marcado": True},
        "tax_class": {"campo": "taxable", "marcado": True},
        "sale_starts_at": {"campo": "sale_price", "preenchido": True},
        "sale_ends_at": {"campo": "sale_price", "preenchido": True},
    }


def lista_variantes(produto):
    """HTML da secao "Variantes" do produto: uma linha por variante; clicar (ou
    "Editar") abre o form dela no modal. Contrato dos data- em admin_lista_modal."""
    salvo = produto.pk is not None
    variantes = list(produto.variantes.prefetch_related("midias")) if salvo else []
    linhas = [{
        "variante": variante,
        "imagem": next(iter(variante.midias.all()), None),
        "url_editar": url_popup("admin:loja_varianteproduto_change", variante.pk),
        "url_excluir": url_popup("admin:loja_varianteproduto_delete", variante.pk),
    } for variante in variantes]
    # Produto que nao e variavel tem uma variante so: sem ela, o botao cadastra;
    # com ela, so se edita (a trava de verdade e o clean() da variante).
    variavel = produto.tipo == produto.Tipo.VARIAVEL
    return render_to_string("admin/loja/lista_variantes.html", {
        "linhas": linhas,
        "pode_adicionar": not salvo or variavel or not variantes,
        "url_adicionar": url_popup(
            "admin:loja_varianteproduto_add", produto=produto.pk, account=produto.account_id
        ) if salvo else None,
    })


@admin.register(VarianteProduto)
class VarianteProdutoAdmin(ConfigVariante, TemaModelAdmin):
    """Lista de SKUs e o formulario do modal de variante."""

    list_display = ["__str__", "sku", "barcode", "price", "inventory_quantity", "stock_status"]
    list_filter = ["stock_status", "manage_inventory"]
    search_fields = ["sku", "barcode", "titulo", "produto__nome"]
    autocomplete_fields = ["produto"]
    # Opcoes (Cor + Tamanho) logo abaixo da identificacao; o resto vem depois ("sh-final").
    inlines = [OpcoesInline]
    fieldsets = [
        ("Variante", {"fields": [
            "produto", ("titulo", "is_default"), ("sku", "barcode"), ("posicao", "active"),
        ]}),
        ("Imagens", {"classes": ["sh-final"], "fields": ["imagens"]}),
        ("Preco", {"classes": ["sh-final"], "fields": PRECO}),
        ("Estoque", {"classes": ["sh-final"], "fields": ESTOQUE}),
        ("Envio", {"classes": ["sh-final"], "fields": ENVIO}),
        ("Impostos", {"classes": ["sh-final"], "fields": IMPOSTOS}),
    ]

    def save_model(self, request, obj, form, change):
        # Titulo em branco: sai das opcoes em save_related (elas so existem depois).
        form.titulo_automatico = not (obj.titulo or "").strip()
        obj.titulo = obj.titulo or "Nova variante"
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        variante = form.instance
        if getattr(form, "titulo_automatico", False):
            opcoes = variante.opcoes.select_related("valor__tipo").order_by(
                "valor__tipo__posicao", "valor__tipo__id"
            )
            titulo = " / ".join(opcao.valor.valor for opcao in opcoes)
            if titulo:
                VarianteProduto.objects.filter(pk=variante.pk).update(titulo=titulo)
