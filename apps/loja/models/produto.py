from django.core.exceptions import ValidationError
from django.db import models

from apps.core.tenant.managers import TenantManager, UnscopedManager
from apps.core.tenant.validators import conta_do_registro

from .base import ComDatas, JSONDecimalField


class ProdutoManager(TenantManager):
    def create(self, **kwargs):
        produto = super().create(**kwargs)
        if produto.tipo == produto.Tipo.SIMPLES:
            from apps.loja.services.variantes import obter_variante_padrao

            obter_variante_padrao(produto)
        return produto


class Produto(ComDatas):
    class Tipo(models.TextChoices):
        SIMPLES = "simple", "Simples"
        VARIAVEL = "variable", "Variavel"
        BUNDLE = "bundle", "Bundle"
        AGRUPADO = "grouped", "Agrupado"
        EXTERNO = "external", "Externo"

    class Status(models.TextChoices):
        PUBLICADO = "publish", "Publicado"
        RASCUNHO = "draft", "Rascunho"
        PENDENTE = "pending", "Pendente"
        PRIVADO = "private", "Privado"
        ARQUIVADO = "archived", "Arquivado"
        LIXEIRA = "trash", "Lixeira"

    class Visibilidade(models.TextChoices):
        VISIVEL = "visible", "Loja e busca"
        CATALOGO = "catalog", "Somente loja"
        BUSCA = "search", "Somente busca"
        OCULTO = "hidden", "Oculto"

    nome = models.CharField("nome", max_length=255)
    slug = models.SlugField("slug", max_length=255, allow_unicode=True)
    descricao = models.TextField("descricao", blank=True)
    descricao_curta = models.TextField("descricao curta", blank=True)
    tipo = models.CharField("tipo", max_length=20, choices=Tipo, default=Tipo.SIMPLES)
    status = models.CharField("status", max_length=20, choices=Status, default=Status.PUBLICADO)
    fornecedor = models.CharField("fornecedor", max_length=150, blank=True)
    marca = models.CharField("marca", max_length=150, blank=True)
    categoria = models.ForeignKey(
        "loja.Categoria", verbose_name="categoria principal", null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="produtos_principais",
    )
    categorias = models.ManyToManyField(
        "loja.Categoria", verbose_name="categorias", blank=True, related_name="produtos"
    )
    tags = models.ManyToManyField(
        "loja.Tag", verbose_name="tags", blank=True, related_name="produtos"
    )
    seo_titulo = models.CharField("titulo SEO", max_length=255, blank=True)
    seo_descricao = models.TextField("descricao SEO", blank=True)
    publicado_em = models.DateTimeField("publicado em", null=True, blank=True)
    destaque = models.BooleanField("destaque", default=False)
    visibilidade = models.CharField(
        "visibilidade", max_length=20, choices=Visibilidade, default="visible"
    )
    url_externa = models.URLField("URL externa", blank=True)
    texto_botao = models.CharField("texto do botao", max_length=100, blank=True)
    avaliacoes_permitidas = models.BooleanField("permite avaliacoes", default=True)
    nota_compra = models.TextField("nota da compra", blank=True)
    ordem_menu = models.IntegerField("ordem no menu", default=0)
    id_pai = models.PositiveBigIntegerField("produto pai (id)", default=0)
    total_vendas = models.PositiveIntegerField("total de vendas", default=0)
    atributos = JSONDecimalField("atributos", default=list, blank=True)

    objects = ProdutoManager()
    all_objects = UnscopedManager()

    class Meta:
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(
            fields=["account", "slug"], name="produto_slug_conta_unico"
        )]

    def __str__(self):
        return self.nome or f"Produto {self.pk}"

    def clean(self):
        super().clean()
        erros = {}
        if self.tipo == self.Tipo.EXTERNO and not self.url_externa:
            # Produto externo e so um link para outra loja: sem URL o botao nao leva a nada.
            erros["url_externa"] = "Produto externo precisa da URL da outra loja."
        if self.pk and self.tipo != self.Tipo.VARIAVEL:
            quantas = self.variantes.model.all_objects.filter(produto_id=self.pk).count()
            if quantas > 1:
                erros["tipo"] = (
                    f"Este produto tem {quantas} variantes; so produto Variavel tem mais de uma. "
                    "Exclua as extras antes de mudar o tipo."
                )
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        if not self.slug:
            from apps.loja.services.slugs import slug_livre

            self.slug = slug_livre(Produto, self.nome, self.pk, conta_do_registro(self))
        super().save(*args, **kwargs)

    @property
    def variante_padrao(self):
        cache = getattr(self, "_variante_padrao_cache", None)
        if cache is None and self.pk:
            # all() usa o prefetch_related da listagem; filter() iria ao banco por linha.
            variantes = list(self.variantes.all())
            cache = next((v for v in variantes if v.is_default), None)
            cache = cache or (variantes[0] if variantes else None)
            self._variante_padrao_cache = cache
        return cache

    def _valor_variante(self, field, default=None):
        variante = self.variante_padrao
        return getattr(variante, field, default) if variante else default

    def estoque_do_bundle(self):
        """(quantidade, variante que limita) do bundle: o componente que acaba primeiro.

        Kit = 1 mouse + 2 pilhas; 10 mouses e 6 pilhas -> 3 kits (6 // 2), limitado
        pelas pilhas. Componente sem controle de estoque nao limita; sem nenhum que
        limite, (None, None) = sem limite.
        """
        limites = [
            (max(item.component_variant.inventory_quantity, 0) // max(item.quantity, 1),
             item.component_variant)
            for item in self.componentes.select_related("component_variant__produto")
            if item.component_variant.manage_inventory
        ]
        return min(limites, key=lambda limite: limite[0]) if limites else (None, None)

    @property
    def estoque(self):
        if self.tipo == self.Tipo.BUNDLE:
            return self.estoque_do_bundle()[0]
        return self._valor_variante("inventory_quantity")

    @property
    def situacao_estoque(self):
        if self.tipo == self.Tipo.BUNDLE:
            quantidade = self.estoque
            return "outofstock" if quantidade is not None and quantidade <= 0 else "instock"
        return self._valor_variante("stock_status", "outofstock")

    sku = property(lambda self: self._valor_variante("sku", ""))
    preco_regular = property(lambda self: self._valor_variante("price"))
    preco_promocional = property(lambda self: self._valor_variante("sale_price"))
    preco = property(lambda self: self._valor_variante("current_price"))

    @property
    def imagens(self):
        """Galeria do produto: primeiro as imagens da variante padrao (a 1a e a capa:
        miniatura da listagem e primeira imagem na API Woo), depois as das outras."""
        def ordem(midia):
            variante = midia.variante
            da_padrao = variante is None or variante.is_default
            return (not da_padrao, variante.posicao if variante else 0, midia.posicao, midia.pk)

        return [
            {"id": item.pk, "src": item.url, "alt": item.alt_text}
            for item in sorted(self.midias.all(), key=ordem)
        ]
