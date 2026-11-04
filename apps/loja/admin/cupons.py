"""Cadastro e regras de elegibilidade dos cupons."""

from django import forms
from django.contrib import admin

from apps.core.admin_base import TemaModelAdmin
from apps.loja.admin.codigo_externo import CodigoExternoMixin
from apps.loja.models import Cupom

DIAS = [
    ("0", "Segunda-feira"), ("1", "Terca-feira"), ("2", "Quarta-feira"),
    ("3", "Quinta-feira"), ("4", "Sexta-feira"), ("5", "Sabado"), ("6", "Domingo"),
]


class CupomForm(forms.ModelForm):
    """Valida as listas M2M e apresenta os dias como multisselecao."""

    dias_semana = forms.MultipleChoiceField(
        label="dias da semana", choices=DIAS, required=False,
        help_text="Sem selecao, o cupom vale todos os dias.",
    )
    LISTAS = {
        ("customer_eligibility", "specific_customers"): ("clientes", "Escolha os clientes."),
        ("customer_eligibility", "customer_tags"): ("tags", "Escolha as tags de clientes."),
        ("product_eligibility", "specific_products"): ("produtos", "Escolha os produtos."),
        ("product_eligibility", "specific_variants"): ("variantes", "Escolha as variantes."),
        ("product_eligibility", "categories"): ("categorias", "Escolha as categorias."),
        ("product_eligibility", "product_tags"): ("tags", "Escolha as tags de produtos."),
    }

    def clean(self):
        dados = super().clean()
        for (campo, valor), (lista, mensagem) in self.LISTAS.items():
            if dados.get(campo) == valor and lista in self.fields and not dados.get(lista):
                self.add_error(lista, mensagem)
        for incluidos, excluidos, nome in (("produtos", "produtos_excluidos", "produto"),
                                           ("categorias", "categorias_excluidas", "categoria")):
            repetidos = set(dados.get(incluidos) or []) & set(dados.get(excluidos) or [])
            if repetidos:
                nomes = ", ".join(sorted(str(item) for item in repetidos))
                self.add_error(excluidos,
                               f"Esta {nome} tambem esta na lista de incluidos: {nomes}.")
        return dados


@admin.register(Cupom)
class CupomAdmin(CodigoExternoMixin, TemaModelAdmin):
    entidade_externa = "cupons"
    form = CupomForm
    list_display = [
        "name", "code", "codigo_externo", "discount_type", "value", "status", "ends_at",
    ]
    list_filter = ["status", "discount_type", "product_eligibility", "customer_eligibility"]
    search_fields = ["name", "code"]
    periodos = [("starts_at", "ends_at")]
    larguras = {
        "minimum_requirement": 4, "minimum_subtotal": 4, "minimum_quantity": 4,
        "subtotal_maximo": 4, "quantidade_maxima": 4,
    }
    condicoes = {
        "value": {"campo": "discount_type", "em": ["percentage", "fixed_amount"]},
        "free_shipping": {"campo": "discount_type", "em": ["percentage", "fixed_amount"]},
        "minimum_subtotal": {
            "campo": "minimum_requirement", "em": ["subtotal", "subtotal_quantity"]},
        "minimum_quantity": {
            "campo": "minimum_requirement", "em": ["quantity", "subtotal_quantity"]},
        "clientes": {"campo": "customer_eligibility", "em": ["specific_customers"]},
        "produtos": {"campo": "product_eligibility", "em": ["specific_products"]},
        "variantes": {"campo": "product_eligibility", "em": ["specific_variants"]},
        "categorias": {"campo": "product_eligibility", "em": ["categories"]},
        "tags": [
            {"campo": "customer_eligibility", "em": ["customer_tags"]},
            {"campo": "product_eligibility", "em": ["product_tags"]},
        ],
    }
    fieldsets = [
        ("Cupom", {"fields": ["name", "code", "description", ("status", "currency")]}),
        ("Desconto", {"fields": [
            ("discount_type", "value"), ("free_shipping", "stacking_policy"),
        ]}),
        ("Agenda", {"fields": [
            ("starts_at", "ends_at"), "dias_semana", ("horario_inicio", "horario_fim"),
        ]}),
        ("Limites de uso", {"fields": [
            ("usage_limit", "usage_limit_per_customer"), "usage_count",
            ("once_per_order", "first_order_only"),
        ]}),
        ("Regras do pedido", {"fields": [
            ("minimum_requirement", "minimum_subtotal", "minimum_quantity"),
            ("subtotal_maximo", "quantidade_maxima"),
            ("produtos_distintos_minimos", "produtos_distintos_maximos"),
        ]}),
        ("Produtos", {"fields": [
            "product_eligibility", "produtos", "variantes", "categorias", "tags",
            ("preco_item_minimo", "preco_item_maximo"),
            "produtos_excluidos", "categorias_excluidas", "excluir_promocao",
        ]}),
        ("Clientes", {"fields": ["customer_eligibility", "clientes"]}),
    ]
    readonly_fields = ["usage_count"]
