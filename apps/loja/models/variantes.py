from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.validators import validar_gtin

from .base import NAO_NEGATIVO, ComDatas, JSONDecimalField


class VarianteProduto(ComDatas):
    class PoliticaEstoque(models.TextChoices):
        NEGAR = "deny", "Nao vender sem estoque"
        CONTINUAR = "continue", "Continuar vendendo"

    class SituacaoEstoque(models.TextChoices):
        EM_ESTOQUE = "instock", "Em estoque"
        SEM_ESTOQUE = "outofstock", "Sem estoque"
        ENCOMENDA = "onbackorder", "Sob encomenda"

    class SituacaoFiscal(models.TextChoices):
        # Valores do WooCommerce (tax_status): a API Woo grava e devolve estes.
        TRIBUTAVEL = "taxable", "Tributavel"
        SO_FRETE = "shipping", "Somente o frete"
        NENHUM = "none", "Nao tributavel"

    produto = models.ForeignKey(
        "loja.Produto", verbose_name="produto", on_delete=models.CASCADE, related_name="variantes"
    )
    titulo = models.CharField("titulo", max_length=255, default="Default")
    sku = models.CharField("SKU", max_length=100, blank=True, db_index=True)
    barcode = models.CharField(
        "codigo de barras", max_length=100, blank=True, db_index=True, validators=[validar_gtin]
    )
    price = models.DecimalField(
        "preco", max_digits=12, decimal_places=2, null=True, blank=True, validators=NAO_NEGATIVO
    )
    compare_at_price = models.DecimalField(
        "preco de comparacao", max_digits=12, decimal_places=2, null=True, blank=True,
        validators=NAO_NEGATIVO
    )
    sale_price = models.DecimalField(
        "preco promocional", max_digits=12, decimal_places=2, null=True, blank=True,
        validators=NAO_NEGATIVO
    )
    cost = models.DecimalField(
        "custo", max_digits=12, decimal_places=2, null=True, blank=True, validators=NAO_NEGATIVO
    )
    sale_starts_at = models.DateTimeField("inicio da promocao", null=True, blank=True)
    sale_ends_at = models.DateTimeField("fim da promocao", null=True, blank=True)
    weight = models.DecimalField(
        "peso", max_digits=12, decimal_places=3, null=True, blank=True, validators=NAO_NEGATIVO
    )
    weight_unit = models.CharField("unidade de peso", max_length=5, default="kg")
    inventory_quantity = models.IntegerField("estoque", default=0)
    inventory_policy = models.CharField(
        "quando acabar o estoque", max_length=10, choices=PoliticaEstoque, default="deny"
    )
    manage_inventory = models.BooleanField("controlar estoque", default=True)
    stock_status = models.CharField(
        "situacao do estoque", max_length=20, choices=SituacaoEstoque, default="instock"
    )
    low_stock_amount = models.IntegerField(
        "estoque minimo", null=True, blank=True, validators=NAO_NEGATIVO
    )
    requires_shipping = models.BooleanField("requer entrega", default=True)
    sold_individually = models.BooleanField("vendido individualmente", default=False)
    virtual = models.BooleanField("virtual", default=False)
    downloadable = models.BooleanField("para download", default=False)
    taxable = models.BooleanField("tributavel", default=True)
    tax_status = models.CharField(
        "situacao fiscal", max_length=20, choices=SituacaoFiscal, default=SituacaoFiscal.TRIBUTAVEL
    )
    tax_class = models.CharField("classe fiscal", max_length=100, blank=True)
    shipping_class = models.CharField("classe de entrega", max_length=100, blank=True)
    dimensions = JSONDecimalField("dimensoes", default=dict, blank=True)
    posicao = models.PositiveIntegerField("posicao", default=0)
    is_default = models.BooleanField("variante padrao", default=False)
    valores = models.ManyToManyField(
        "loja.ValorVariante", verbose_name="valores", through="ValorDaVarianteProduto", blank=True
    )

    class Meta:
        verbose_name = "variante"
        verbose_name_plural = "variantes"
        ordering = ["posicao", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "sku"], condition=~Q(sku=""), name="variante_sku_conta_unico"
            ),
            models.UniqueConstraint(
                fields=["account", "barcode"], condition=~Q(barcode=""),
                name="variante_barcode_conta_unico",
            ),
            models.UniqueConstraint(
                fields=["produto"], condition=Q(is_default=True), name="variante_default_produto"
            ),
        ]

    def __str__(self):
        nome = self.produto.nome if self.produto_id else ""
        titulo = "" if self.is_default else self.titulo
        return " - ".join(filter(None, [nome, titulo, self.sku]))

    def clean(self):
        super().clean()
        erros = {}
        if None not in (self.sale_price, self.price) and self.sale_price > self.price:
            erros["sale_price"] = "O preco promocional nao pode passar do preco normal."
        if self.sale_starts_at and self.sale_ends_at and self.sale_ends_at <= self.sale_starts_at:
            erros["sale_ends_at"] = "O fim da promocao deve ser depois do inicio."
        if self.produto_id and self._outras_do_produto().exists():
            tipo = self.produto.tipo
            if tipo != self.produto.Tipo.VARIAVEL:
                # Simples, externo, agrupado: UMA variante (preco e estoque). Bundle nao
                # precisa de nenhuma (e a soma dos componentes), mas tambem nao tem varias.
                erros["produto"] = (
                    f"Produto do tipo {self.produto.get_tipo_display()} tem uma variante so. "
                    "Para cadastrar varias, mude o tipo do produto para Variavel."
                )
        if erros:
            raise ValidationError(erros)

    def _outras_do_produto(self):
        # all_objects: a regra e do produto, vale mesmo com o superusuario em outra conta.
        return VarianteProduto.all_objects.filter(produto_id=self.produto_id).exclude(pk=self.pk)

    @property
    def current_price(self):
        if self.sale_price is None:
            return self.price
        now = timezone.now()
        if self.sale_starts_at and now < self.sale_starts_at:
            return self.price
        if self.sale_ends_at and now > self.sale_ends_at:
            return self.price
        return self.sale_price

    def save(self, *args, **kwargs):
        if self.produto_id and not self.account_id:
            self.account_id = self.produto.account_id
        # Bundle nao tem estoque proprio: e calculado pelos componentes (Produto.estoque).
        if self.produto_id and self.produto.tipo == self.produto.Tipo.BUNDLE:
            self.manage_inventory = False
        # A primeira variante do produto e a padrao (preco do produto e capa).
        if self._state.adding and self.produto_id and not self._outras_do_produto().exists():
            self.is_default = True
        if self.manage_inventory:
            if self.inventory_quantity > 0:
                self.stock_status = self.SituacaoEstoque.EM_ESTOQUE
            elif self.inventory_policy == self.PoliticaEstoque.CONTINUAR:
                self.stock_status = self.SituacaoEstoque.ENCOMENDA
            else:
                self.stock_status = self.SituacaoEstoque.SEM_ESTOQUE
        super().save(*args, **kwargs)
