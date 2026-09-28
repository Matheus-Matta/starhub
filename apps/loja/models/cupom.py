from django.core.exceptions import ValidationError
from django.db import models

from .base import NAO_NEGATIVO, ComDatas, JSONDecimalField


class Cupom(ComDatas):
    class TipoDesconto(models.TextChoices):
        PERCENTUAL = "percentage", "Percentual"
        VALOR_FIXO = "fixed_amount", "Valor fixo"
        FRETE_GRATIS = "free_shipping", "Frete gratis"

    class Status(models.TextChoices):
        RASCUNHO = "draft", "Rascunho"
        ATIVO = "active", "Ativo"
        PAUSADO = "paused", "Pausado"
        EXPIRADO = "expired", "Expirado"

    class RequisitoMinimo(models.TextChoices):
        NENHUM = "none", "Nenhum"
        SUBTOTAL = "subtotal", "Subtotal"
        QUANTIDADE = "quantity", "Quantidade"

    class ElegibilidadeCliente(models.TextChoices):
        TODOS = "all", "Todos"
        CLIENTES = "specific_customers", "Clientes especificos"
        TAGS = "customer_tags", "Tags de clientes"

    class Combinacao(models.TextChoices):
        NAO_COMBINA = "deny", "Nao combina com outros cupons"
        COMBINA = "allow", "Combina com outros cupons"

    class ElegibilidadeProduto(models.TextChoices):
        TODOS = "all", "Todos"
        PRODUTOS = "specific_products", "Produtos especificos"
        VARIANTES = "specific_variants", "Variantes especificas"
        CATEGORIAS = "categories", "Categorias"
        TAGS = "product_tags", "Tags de produtos"

    code = models.CharField("codigo", max_length=100)
    name = models.CharField("nome", max_length=150)
    description = models.TextField("descricao", blank=True)
    discount_type = models.CharField("tipo de desconto", max_length=20, choices=TipoDesconto)
    value = models.DecimalField(
        "valor", max_digits=12, decimal_places=2, default=0, validators=NAO_NEGATIVO
    )
    currency = models.CharField("moeda", max_length=3, default="BRL")
    status = models.CharField(max_length=20, choices=Status, default=Status.RASCUNHO)
    starts_at = models.DateTimeField("inicio", null=True, blank=True)
    ends_at = models.DateTimeField("termino", null=True, blank=True)
    usage_limit = models.PositiveIntegerField("limite de usos", null=True, blank=True)
    usage_limit_per_customer = models.PositiveIntegerField(
        "limite de usos por cliente", null=True, blank=True
    )
    usage_count = models.PositiveIntegerField("usos", default=0)
    minimum_requirement = models.CharField("requisito minimo",
        max_length=20, choices=RequisitoMinimo, default=RequisitoMinimo.NENHUM
    )
    minimum_subtotal = models.DecimalField(
        "subtotal minimo", max_digits=12, decimal_places=2, null=True, blank=True,
        validators=NAO_NEGATIVO,
    )
    minimum_quantity = models.PositiveIntegerField("quantidade minima", null=True, blank=True)
    customer_eligibility = models.CharField("clientes elegiveis",
        max_length=30, choices=ElegibilidadeCliente, default=ElegibilidadeCliente.TODOS
    )
    product_eligibility = models.CharField("produtos elegiveis",
        max_length=30, choices=ElegibilidadeProduto, default=ElegibilidadeProduto.TODOS
    )
    once_per_order = models.BooleanField("uma vez por pedido", default=True)
    first_order_only = models.BooleanField("so no primeiro pedido", default=False)
    free_shipping = models.BooleanField("frete gratis", default=False)
    stacking_policy = models.CharField(
        "combinacao com outros cupons", max_length=30, choices=Combinacao,
        default=Combinacao.NAO_COMBINA,
    )
    metadata = JSONDecimalField("dados extras", default=dict, blank=True)
    produtos = models.ManyToManyField("loja.Produto", blank=True, related_name="cupons")
    variantes = models.ManyToManyField("loja.VarianteProduto", blank=True, related_name="cupons")
    categorias = models.ManyToManyField("loja.Categoria", blank=True, related_name="cupons")
    tags = models.ManyToManyField("loja.Tag", blank=True, related_name="cupons")
    clientes = models.ManyToManyField("loja.Cliente", blank=True, related_name="cupons")

    class Meta:
        verbose_name = "cupom"
        verbose_name_plural = "cupons"
        constraints = [models.UniqueConstraint(
            fields=["account", "code"], name="cupom_codigo_conta_unico"
        )]

    def clean(self):
        super().clean()
        erros = {}
        if self.discount_type == self.TipoDesconto.PERCENTUAL and not 0 < self.value <= 100:
            erros["value"] = "O percentual deve ficar entre 0 e 100."
        if self.discount_type == self.TipoDesconto.VALOR_FIXO and not self.value > 0:
            erros["value"] = "Informe o valor do desconto."
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            erros["ends_at"] = "O termino deve ser posterior ao inicio."
        # O requisito escolhido pede o numero dele (o campo so aparece nesse caso).
        requisito = self.minimum_requirement
        if requisito == self.RequisitoMinimo.SUBTOTAL and not self.minimum_subtotal:
            erros["minimum_subtotal"] = "Informe o subtotal minimo."
        if requisito == self.RequisitoMinimo.QUANTIDADE and not self.minimum_quantity:
            erros["minimum_quantity"] = "Informe a quantidade minima."
        if erros:
            raise ValidationError(erros)

    def __str__(self):
        return self.code
