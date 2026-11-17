from apps.loja.models import Produto, VarianteProduto
from apps.woo_api.erros import WooErro, id_invalido
from apps.woo_api.recursos import produtos_variacao as variacao
from apps.woo_api.recursos.base import Recurso, booleano, escolha, inteiro
from apps.woo_api.recursos.produtos_entrada import _variant_fields, erro_sku, gravar_produto
from apps.woo_api.recursos.produtos_saida import produto_para_woo


def skus_do_filtro(params):
    return [s.strip() for s in (params.get("sku") or "").split(",") if s.strip()]


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
            qs = qs.filter(variantes__sku__in=skus_do_filtro(params))
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

    # Id de variacao (produtos_variacao.py): o produto dela, marcado com a variacao.
    def obter(self, pk):
        variante = variacao.variante_do_id(pk)
        if variante is None:
            return super().obter(pk)
        try:
            return variacao.marcar(self.queryset().get(pk=variante.produto_id), variante)
        except Produto.DoesNotExist as erro:
            raise id_invalido(self.nome) from erro

    def obter_para_escrita(self, pk):
        variante = variacao.variante_do_id(pk, travar=True)
        if variante is None:
            return super().obter_para_escrita(pk)
        return variacao.marcar(Produto.objects.select_for_update().get(pk=variante.produto_id),
                               variante)

    def para_woo(self, obj):
        variante = variacao.variacao_de(obj)
        if variante is not None:
            return variacao.variacao_para_woo(obj, variante, self.request)
        return produto_para_woo(obj, self.request)

    def para_lista(self, itens):
        skus = set(skus_do_filtro(self.request.query_params)) if self.request else set()
        if not skus:
            return super().para_lista(itens)
        return [linha for obj in itens
                for linha in variacao.linhas_por_sku(obj, skus, self.request)]

    def gravar(self, obj, dados, criando):
        variante = variacao.variacao_de(obj)
        if variante is not None:
            # Id da variacao: so os campos dela; nome, texto e categorias sao do pai.
            _variant_fields(variante, dados)
            variante.save()
            return obj
        return gravar_produto(obj, dados, criando)

    def excluir(self, obj, forcar):
        if variacao.variacao_de(obj) is not None:
            # Sem isto o id da variacao mandaria o produto inteiro para a lixeira.
            raise WooErro("woocommerce_rest_cannot_delete",
                          "A variacao nao e excluida pela API; exclua no admin do hub.", 400)
        return super().excluir(obj, forcar)

    def erro_integridade(self, erro):
        # Duas gravacoes com o mesmo SKU ao mesmo tempo: o indice unico barrou.
        return erro_sku("")
