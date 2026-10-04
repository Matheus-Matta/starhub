"""Cadastros de apoio do catalogo: categoria, tag, tipos/valores de variante e cupom."""

from django import forms
from django.contrib import admin
from django.db.models import Count
from django.template.loader import render_to_string

from apps.core.admin_base import TemaModelAdmin, TemaTabularInline
from apps.loja.admin import campos
from apps.loja.admin.codigo_externo import CodigoExternoMixin
from apps.loja.models import Categoria, Cupom, Tag, TipoVariante, ValorVariante


@admin.register(Categoria)
class CategoriaAdmin(CodigoExternoMixin, TemaModelAdmin):
    entidade_externa = "categorias"
    campos_json = campos.CATEGORIA
    list_display = ["categoria_info", "codigo_externo", "pai", "ordem", "qtd_produtos"]
    list_display_links = ["categoria_info"]
    search_fields = ["nome", "slug"]
    list_filter = ["pai"]
    prepopulated_fields = {"slug": ["nome"]}
    fields = ["nome", "slug", "pai", "descricao", "imagem", "exibicao", "ordem"]

    @admin.display(description="categoria", ordering="nome")
    def categoria_info(self, obj):
        imagem = obj.imagem if isinstance(obj.imagem, dict) else {}
        return render_to_string("components/table_produto.html", {
            "icone": "layout-list",
            "imagem_url": imagem.get("src", ""),
            "meta": f"Slug: {obj.slug}",
            "nome": obj.nome,
        })

    def get_queryset(self, request):
        # Contagem na consulta da lista: um .count() por linha era N+1.
        return super().get_queryset(request).select_related("pai").annotate(
            total_produtos=Count("produtos", distinct=True))

    @admin.display(description="produtos", ordering="total_produtos")
    def qtd_produtos(self, obj):
        return obj.total_produtos


@admin.register(Tag)
class TagAdmin(TemaModelAdmin):
    list_display = ["nome", "slug", "updated_at"]
    search_fields = ["nome", "slug"]
    fields = ["nome", "slug"]


class ValorVarianteInline(TemaTabularInline):
    model = ValorVariante
    extra = 0
    verbose_name, verbose_name_plural = "valor", "valores"
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
        # Incluido e excluido ao mesmo tempo: a exclusao ganharia sem ninguem perceber.
        for incluidos, excluidos, nome in (("produtos", "produtos_excluidos", "produto"),
                                           ("categorias", "categorias_excluidas", "categoria")):
            repetidos = set(dados.get(incluidos) or []) & set(dados.get(excluidos) or [])
            if repetidos:
                nomes = ", ".join(sorted(str(item) for item in repetidos))
                mensagem = f"Esta {nome} tambem esta na lista de incluidos: {nomes}."
                self.add_error(excluidos, mensagem)
        return dados


@admin.register(Cupom)
class CupomAdmin(CodigoExternoMixin, TemaModelAdmin):
    entidade_externa = "cupons"
    form = CupomForm
    list_display = [
        "name", "codigo_externo", "discount_type", "value", "status", "usage_count", "ends_at",
    ]
    list_filter = ["status", "discount_type", "product_eligibility", "customer_eligibility"]
    search_fields = ["name"]
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
        ("Cupom", {"fields": ["name", "description", ("status", "currency")]}),
        ("Desconto", {"fields": [
            ("discount_type", "value"), ("free_shipping", "stacking_policy"),
            ("starts_at", "ends_at"),
        ]}),
        ("Limites", {"fields": [
            ("usage_limit", "usage_limit_per_customer"), "usage_count",
            ("once_per_order", "first_order_only"),
            ("minimum_requirement", "minimum_subtotal", "minimum_quantity"),
        ]}),
        # Onde o desconto vale: a elegibilidade e, por cima dela, as excecoes
        # (apps/loja/services/cupons.py aplica as duas).
        ("Produtos", {"fields": [
            "product_eligibility", "produtos", "variantes", "categorias", "tags",
            "produtos_excluidos", "categorias_excluidas", "excluir_promocao",
        ]}),
        ("Clientes", {"fields": ["customer_eligibility", "clientes"]}),
    ]
    readonly_fields = ["usage_count"]
