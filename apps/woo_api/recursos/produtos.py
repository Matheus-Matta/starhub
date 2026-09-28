from apps.loja.models import Produto, VarianteProduto
from apps.woo_api.recursos.base import Recurso, booleano, escolha, inteiro
from apps.woo_api.recursos.produtos_entrada import erro_sku, gravar_produto
from apps.woo_api.recursos.produtos_saida import produto_para_woo


class ProdutoRecurso(Recurso):
    modelo = Produto
    nome = "product"
    campo_busca = ("nome", "variantes__sku", "descricao_curta")
    ordenacoes = {
        "id": "id", "include": "id", "date": "created_at", "modified": "updated_at",
        "title": "nome", "slug": "slug", "price": "variantes__price",
        "popularity": "total_vendas", "menu_order": "ordem_menu",
    }

    def queryset(self):
        return Produto.objects.prefetch_related(
            "categorias", "tags", "midias__variante", "variantes"
        )

    def filtrar(self, qs, params):
        status = params.get("status") or "any"
        if status == "any":
            # "any" do WordPress nao inclui a lixeira.
            qs = qs.exclude(status=Produto.Status.LIXEIRA)
        else:
            qs = qs.filter(status=escolha(status, "status", Produto.Status.values))
        if params.get("sku"):
            values = [s.strip() for s in params["sku"].split(",") if s.strip()]
            qs = qs.filter(variantes__sku__in=values)
        if params.get("type"):
            qs = qs.filter(tipo=escolha(params["type"], "type", Produto.Tipo.values))
        if params.get("featured") not in (None, ""):
            qs = qs.filter(destaque=booleano(params["featured"], "featured"))
        if params.get("category"):
            ids = [inteiro(c, "category") for c in params["category"].split(",") if c.strip()]
            qs = qs.filter(categorias__id__in=ids).distinct()
        if params.get("stock_status"):
            qs = qs.filter(variantes__stock_status=escolha(
                params["stock_status"], "stock_status", VarianteProduto.SituacaoEstoque.values
            ))
        if params.get("parent"):
            qs = qs.filter(id_pai__in=[inteiro(p, "parent") for p in params["parent"].split(",")])
        if params.get("slug"):
            qs = qs.filter(slug=params["slug"])
        return super().filtrar(qs, params).distinct()

    def para_woo(self, obj):
        return produto_para_woo(obj, getattr(self, "request", None))

    def gravar(self, obj, dados, criando):
        return gravar_produto(obj, dados, criando)

    def erro_integridade(self, erro):
        # Duas gravacoes com o mesmo SKU ao mesmo tempo: o indice unico barrou.
        return erro_sku("")
