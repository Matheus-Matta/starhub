from django.contrib import admin
from django.template.loader import render_to_string

from apps.core.admin_base import TemaModelAdmin
from apps.core.admin_utils import (
    acoes_da_linha,
    badge_status,
    imagem_principal,
    na_listagem,
    valor_moeda,
)
from apps.core.filtros import FiltroPeriodo
from apps.loja.admin import campos
from apps.loja.admin.bundle import ComponenteInline, estoque_calculado
from apps.loja.admin.codigo_externo import CodigoExternoMixin
from apps.loja.admin.detalhes import variacoes_do_produto
from apps.loja.admin.variante_unica import VarianteUnicaInline
from apps.loja.admin.variantes import lista_variantes
from apps.loja.models import Produto, VarianteProduto
from apps.loja.services.servicos_regras import servicos_do_produto

# Tres jeitos de mostrar o produto, pelo tipo (condicoes.js troca na hora):
#   simples/externo/agrupado: a variante unica vira secoes da pagina (Preco, Estoque...);
#   variavel: lista de variantes, cada uma no modal com as opcoes (Cor, Tamanho);
#   bundle: secoes da variante unica SEM estoque + lista de componentes.
UNICA = ["simple", "external", "grouped", "bundle"]


@admin.register(Produto)
class ProdutoAdmin(CodigoExternoMixin, TemaModelAdmin):
    entidade_externa = "produtos"
    campos_json = campos.PRODUTO
    list_display = [
        "produto_info", "codigo_externo", "preco_regular_fmt", "preco_promocional_fmt",
        "estoque", "situacao_estoque_badge", "status_badge", "updated_at", "acoes",
    ]
    list_display_links = ["produto_info"]
    list_filter = [
        ("created_at", FiltroPeriodo), "status", "variantes__stock_status", "tipo", "destaque",
        "categorias", "origin",
    ]
    search_fields = ["nome", "variantes__sku", "variantes__barcode", "slug"]
    list_per_page = 25
    readonly_fields = ["lista_variantes", "estoque_bundle", "servicos_do_produto",
                       "total_vendas", "created_at", "updated_at"]
    # Campo so de leitura que ocupa a linha toda (tabela), e nao meia coluna.
    readonly_largos = ["lista_variantes", "estoque_bundle", "servicos_do_produto"]
    inlines = [VarianteUnicaInline, ComponenteInline]
    condicoes = {
        "#variantes-group": {"campo": "tipo", "em": UNICA},
        ".secao-estoque": {"campo": "tipo", "em": ["simple", "external", "grouped"]},
        ".secao-variantes": {"campo": "tipo", "em": ["variable"]},
        "#componentes-group": {"campo": "tipo", "em": ["bundle"]},
        ".secao-estoque-bundle": {"campo": "tipo", "em": ["bundle"]},
        "url_externa": {"campo": "tipo", "em": ["external"]},
        "texto_botao": {"campo": "tipo", "em": ["external"]},
    }
    fieldsets = [
        ("Geral", {"fields": [
            ("nome", "slug"), ("tipo", "status"), ("visibilidade", "destaque"),
            ("fornecedor", "marca"), "categoria", "categorias", "tags",
        ]}),
        # secao-variantes: condicoes acima; secao-lista: desenho da lista (lista-modal.css).
        ("Variantes", {"classes": ["secao-variantes", "secao-lista"],
                       "fields": ["lista_variantes"]}),
        ("Estoque", {"classes": ["secao-estoque-bundle"], "fields": ["estoque_bundle"]}),
        # "sh-final": depois das secoes da variante (Preco, Estoque...) e dos componentes.
        ("Servicos", {"classes": ["sh-final"], "fields": ["servicos_do_produto"]}),
        ("Descricao", {"classes": ["collapse", "sh-final"],
                       "fields": ["descricao_curta", "descricao"]}),
        ("SEO", {"classes": ["collapse", "sh-final"], "fields": ["seo_titulo", "seo_descricao"]}),
        ("Atributos", {"classes": ["collapse", "sh-final"], "fields": ["atributos"]}),
        ("Avancado", {"classes": ["collapse", "sh-final"], "fields": [
            "metadados", ("url_externa", "texto_botao"), ("ordem_menu", "id_pai"),
            ("avaliacoes_permitidas", "nota_compra"), "publicado_em",
            "total_vendas", ("created_at", "updated_at"),
        ]}),
    ]

    def get_queryset(self, request):
        produtos = super().get_queryset(request)
        if not na_listagem(request):
            return produtos
        # Imagens e opcoes das variantes: miniatura e linha de detalhe (coluna "Acoes").
        return produtos.prefetch_related(
            "variantes__midias", "variantes__opcoes__valor__tipo", "midias__variante"
        )

    @admin.display(description="acoes")
    def acoes(self, obj):
        # So o variavel tem varias variantes para abrir; os outros, so o lapis.
        if obj.tipo == Produto.Tipo.VARIAVEL:
            return variacoes_do_produto(obj)
        return acoes_da_linha(obj)

    @admin.display(description="Variantes")
    def lista_variantes(self, obj):
        return lista_variantes(obj)

    @admin.display(description="Estoque")
    def estoque_bundle(self, obj):
        return estoque_calculado(obj)

    @admin.display(description="Servicos")
    def servicos_do_produto(self, obj):
        # Vem das regras de cada servico (Loja > Servicos); aqui so se consulta.
        return render_to_string("admin/loja/servicos_do_produto.html", {
            "servicos": servicos_do_produto(obj) if obj and obj.pk else [],
        })

    @admin.display(description="produto", ordering="nome")
    def produto_info(self, obj):
        return render_to_string("components/table_produto.html", {
            "imagem_url": imagem_principal(obj.imagens),
            "nome": obj.nome or f"Produto {obj.pk}",
            "sku": obj.sku or "-",
        })

    @admin.display(description="preco")
    def preco_regular_fmt(self, obj):
        return valor_moeda(obj.preco_regular)

    @admin.display(description="promocional")
    def preco_promocional_fmt(self, obj):
        return valor_moeda(obj.preco_promocional) if obj.preco_promocional is not None else "-"

    @admin.display(description="estoque")
    def situacao_estoque_badge(self, obj):
        situacao = VarianteProduto.SituacaoEstoque(obj.situacao_estoque)
        return badge_status(situacao.value, situacao.label)

    @admin.display(description="status", ordering="status")
    def status_badge(self, obj):
        return badge_status(obj.status, obj.get_status_display())
