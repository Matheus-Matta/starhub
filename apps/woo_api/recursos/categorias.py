from django.db.models import Count
from django.utils.text import slugify

from apps.loja.models import Categoria
from apps.loja.services.slugs import slug_livre
from apps.woo_api.erros import WooErro, parametro_invalido
from apps.woo_api.recursos.base import Recurso, booleano, escolha, inteiro, texto
from apps.woo_api.recursos.produtos_saida import url_absoluta


class CategoriaRecurso(Recurso):
    modelo = Categoria
    nome = "term"
    campo_busca = ("nome", "slug")
    ordenacoes = {"id": "id", "name": "nome", "slug": "slug", "count": "qtd", "include": "id"}
    ordenacao_padrao = ("name", "asc")
    suporta_lixeira = False

    def queryset(self):
        return Categoria.objects.annotate(qtd=Count("produtos"))

    def filtrar(self, qs, params):
        if params.get("slug"):
            qs = qs.filter(slug=params["slug"])
        if params.get("parent") not in (None, ""):
            pai = inteiro(params["parent"], "parent")
            qs = qs.filter(pai_id=pai or None)
        if params.get("product"):
            qs = qs.filter(produtos__id=inteiro(params["product"], "product"))
        if booleano(params.get("hide_empty", False), "hide_empty"):
            qs = qs.filter(qtd__gt=0)
        return super().filtrar(qs, params)

    def para_woo(self, obj):
        return {
            "id": obj.pk,
            "name": obj.nome,
            "slug": obj.slug,
            "parent": obj.pai_id or 0,
            "description": obj.descricao,
            "display": obj.exibicao,
            "image": ({**obj.imagem, "src": url_absoluta(obj.imagem.get("src"), self.request)}
                      if isinstance(obj.imagem, dict) else obj.imagem),
            "menu_order": obj.ordem,
            "count": obj.qtd if hasattr(obj, "qtd") else obj.produtos.count(),
        }

    def gravar(self, obj, dados, criando):
        if criando and not dados.get("name"):
            raise WooErro("rest_missing_callback_param", "Parametro(s) ausente(s): name", 400,
                          {"params": ["name"]})
        if "name" in dados:
            obj.nome = texto(dados["name"], "name", 200)
        if "parent" in dados:
            pai = inteiro(dados["parent"], "parent")
            if pai and not Categoria.objects.filter(pk=pai).exists():
                raise parametro_invalido("parent", "Categoria pai nao existe.")
            if pai and pai == obj.pk:
                raise parametro_invalido("parent", "A categoria nao pode ser pai dela mesma.")
            obj.pai_id = pai or None
        if "description" in dados:
            obj.descricao = texto(dados["description"], "description")
        if "display" in dados:
            obj.exibicao = escolha(dados["display"], "display", Categoria.Exibicao.values)
        if "image" in dados:
            obj.imagem = dados["image"] or None
        if "menu_order" in dados:
            obj.ordem = inteiro(dados["menu_order"], "menu_order")
        if criando:
            self._barrar_repetida(obj)
        if dados.get("slug"):
            slug = slugify(str(dados["slug"]), allow_unicode=True)
            if Categoria.objects.filter(slug=slug).exclude(pk=obj.pk).exists():
                raise parametro_invalido("slug", "Ja existe uma categoria com esse slug.")
            obj.slug = slug
        elif criando:
            # Mesmo nome sob outro pai e permitido; o slug ganha sufixo (-2, -3).
            obj.slug = slug_livre(Categoria, obj.nome)
        obj.save()
        return obj

    def _barrar_repetida(self, obj):
        # O WordPress recusa nome repetido sob o mesmo pai e devolve o id da que ja
        # existe (resource_id). ERPs usam isso para "criar ou reaproveitar".
        existente = Categoria.objects.filter(nome__iexact=obj.nome, pai_id=obj.pai_id).first()
        if existente:
            raise WooErro(
                "term_exists", "Ja existe uma categoria com esse nome neste nivel.", 400,
                {"resource_id": existente.pk},
            )

    def erro_integridade(self, erro):
        return WooErro("term_exists", "Ja existe uma categoria com esse nome/slug.", 400)
