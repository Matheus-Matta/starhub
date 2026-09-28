"""Cadastros de apoio do catalogo: categoria, tag, tipos/valores de variante e cupom."""

from django import forms
from django.contrib import admin

from apps.core.admin_base import TemaModelAdmin, TemaTabularInline
from apps.loja.admin import campos
from apps.loja.models import Categoria, Cupom, Tag, TipoVariante, ValorVariante


@admin.register(Categoria)
class CategoriaAdmin(TemaModelAdmin):
    campos_json = campos.CATEGORIA
    list_display = ["nome", "slug", "pai", "ordem", "qtd_produtos"]
    search_fields = ["nome", "slug"]
    list_filter = ["pai"]
    prepopulated_fields = {"slug": ["nome"]}
    fields = ["nome", "slug", "pai", "descricao", "imagem", "exibicao", "ordem"]

    @admin.display(description="produtos")
    def qtd_produtos(self, obj):
        return obj.produtos.count()


@admin.register(Tag)
class TagAdmin(TemaModelAdmin):
    list_display = ["nome", "slug", "updated_at"]
    search_fields = ["nome", "slug"]
    fields = ["nome", "slug"]


class ValorVarianteInline(TemaTabularInline):
    model = ValorVariante
    extra = 0
    fields = ["valor", "posicao"]


@admin.register(TipoVariante)
class TipoVarianteAdmin(TemaModelAdmin):
    """Cor, Tamanho...: globais da conta, reaproveitados por qualquer produto."""

    list_display = ["nome", "valores_fmt", "posicao"]
    search_fields = ["nome", "valores__valor"]
    fields = ["nome", "posicao"]
    inlines = [ValorVarianteInline]

    @admin.display(description="valores")
    def valores_fmt(self, obj):
        return ", ".join(valor.valor for valor in obj.valores.all()) or "-"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("valores")


@admin.register(ValorVariante)
class ValorVarianteAdmin(TemaModelAdmin):
    """Sem item no menu (os valores se editam na tela do tipo). Existe para o "+"
    de "Opcoes de variante" do produto criar um valor novo no modal."""

    fields = ["tipo", "valor", "posicao"]
    search_fields = ["valor", "tipo__nome"]
    list_display = ["__str__", "posicao"]

    def has_module_permission(self, request):
        return False


class CupomForm(forms.ModelForm):
    """Elegibilidade escolhida pede a lista dela: "Produtos especificos" sem produto
    nenhum viraria um cupom que nao vale para nada. Fica no form porque as listas
    (ManyToMany) so existem aqui antes de salvar; o model nao as ve no clean()."""

    # elegibilidade escolhida -> (campo da lista, mensagem)
    LISTAS = {
        ("customer_eligibility", "specific_customers"): ("clientes", "Escolha os clientes."),
        ("customer_eligibility", "customer_tags"): ("tags", "Escolha as tags de clientes."),
        ("product_eligibility", "specific_products"): ("produtos", "Escolha os produtos."),
        ("product_eligibility", "specific_variants"): ("variantes", "Escolha as variantes."),
        ("product_eligibility", "categories"): ("categorias", "Escolha as categorias."),
        ("product_eligibility", "product_tags"): ("tags", "Escolha as tags de produtos."),
    }

    # Sem Meta: o CupomAdmin monta o form com o model e os campos das secoes.

    def clean(self):
        dados = super().clean()
        for (campo, valor), (lista, mensagem) in self.LISTAS.items():
            if dados.get(campo) == valor and lista in self.fields and not dados.get(lista):
                self.add_error(lista, mensagem)
        return dados


@admin.register(Cupom)
class CupomAdmin(TemaModelAdmin):
    form = CupomForm
    list_display = ["code", "name", "discount_type", "value", "status", "usage_count", "ends_at"]
    list_filter = ["status", "discount_type", "product_eligibility", "customer_eligibility"]
    search_fields = ["code", "name"]
    periodos = [("starts_at", "ends_at")]
    larguras = {"minimum_requirement": 4, "minimum_subtotal": 4, "minimum_quantity": 4}
    condicoes = {
        # Frete gratis como tipo de desconto nao tem valor; nos outros, o switch soma frete gratis.
        "value": {"campo": "discount_type", "em": ["percentage", "fixed_amount"]},
        "free_shipping": {"campo": "discount_type", "em": ["percentage", "fixed_amount"]},
        "minimum_subtotal": {"campo": "minimum_requirement", "em": ["subtotal"]},
        "minimum_quantity": {"campo": "minimum_requirement", "em": ["quantity"]},
        "clientes": {"campo": "customer_eligibility", "em": ["specific_customers"]},
        "produtos": {"campo": "product_eligibility", "em": ["specific_products"]},
        "variantes": {"campo": "product_eligibility", "em": ["specific_variants"]},
        "categorias": {"campo": "product_eligibility", "em": ["categories"]},
        # Uma lista de tags serve as duas elegibilidades: aparece se qualquer uma pedir.
        "tags": [
            {"campo": "customer_eligibility", "em": ["customer_tags"]},
            {"campo": "product_eligibility", "em": ["product_tags"]},
        ],
    }
    fieldsets = [
        ("Cupom", {"fields": [("code", "name"), "description", ("status", "currency")]}),
        ("Desconto", {"fields": [
            ("discount_type", "value"), ("free_shipping", "stacking_policy"),
            ("starts_at", "ends_at"),
        ]}),
        ("Limites", {"fields": [
            ("usage_limit", "usage_limit_per_customer"), "usage_count",
            ("once_per_order", "first_order_only"),
            ("minimum_requirement", "minimum_subtotal", "minimum_quantity"),
        ]}),
        ("Elegibilidade", {"fields": [
            ("customer_eligibility", "product_eligibility"),
            "produtos", "variantes", "categorias", "tags", "clientes",
        ]}),
    ]
    readonly_fields = ["usage_count"]
