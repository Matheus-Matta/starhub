"""Cadastros de apoio do catalogo: categoria, tag, tipos/valores de variante e cupom."""

from django.contrib import admin
from django.db.models import Count
from django.template.loader import render_to_string

from apps.core.admin_base import TemaModelAdmin, TemaTabularInline
from apps.loja.admin import campos
from apps.loja.admin.codigo_externo import CodigoExternoMixin
from apps.loja.models import Categoria, Tag, TipoVariante, ValorVariante


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
