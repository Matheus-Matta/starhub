from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from .base import NAO_NEGATIVO, ComDatas


def sku_do_servico(nome):
    """SKU que o servico ganha ao nascer sozinho: "Montagem" -> "SERV-MONTAGEM"."""
    return f"SERV-{slugify(nome).upper()}"[:100]


class Servico(ComDatas):
    """Servico extra vendido junto com o item (montagem, impermeabilizacao, garantia).

    Nao e Produto de proposito: produto do hub vai para as lojas como item a venda.
    O pedido guarda o nome, a opcao e o preco que o cliente pagou; daqui saem o id e o
    SKU que o ERP usa para reconhecer o servico (API Woo, meta "starhub" do item).
    """

    nome = models.CharField("nome", max_length=150)
    nome_normalizado = models.CharField(max_length=150, editable=False)
    sku = models.CharField(
        "SKU", max_length=100,
        help_text="Codigo do servico no ERP. Nasce como SERV-<NOME> quando o servico chega "
                  "num pedido sem cadastro; troque pelo codigo do ERP.",
    )
    preco = models.DecimalField(
        "preco padrao", max_digits=12, decimal_places=2, default=Decimal("0.00"),
        validators=NAO_NEGATIVO,
        help_text="Vale para os produtos das regras que nao tem preco proprio.",
    )

    class Meta:
        verbose_name = "servico"
        verbose_name_plural = "servicos"
        ordering = ["nome"]
        constraints = [
            # Dois pedidos chegando juntos com um servico novo: o banco segura o repetido.
            models.UniqueConstraint(fields=["account", "nome_normalizado"],
                                    name="servico_nome_conta_unico"),
            models.UniqueConstraint(fields=["account", "sku"], name="servico_sku_conta_unico"),
        ]

    def save(self, *args, **kwargs):
        self.nome = self.nome.strip()
        self.nome_normalizado = self.nome.casefold()
        self.sku = (self.sku or sku_do_servico(self.nome)).strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome


class RegraServico(ComDatas):
    """A quais produtos o servico vale e por qual preco (uma regra por linha).

Selecao dinamica (categoria "Sofas" E preco ate 2.000) mais os produtos escolhidos
    a mao. Para cada produto vale a primeira regra ativa que casa, pela ordem (menor
    primeiro); e ela que da o preco. Regras em apps/loja/services/servicos_regras.py.
    """

    servico = models.ForeignKey(Servico, verbose_name="servico", on_delete=models.CASCADE,
                                related_name="regras")
    ordem = models.PositiveIntegerField(
        "ordem", default=10,
        help_text="Menor primeiro. O produto que cai em duas regras fica com a de menor ordem.")
    produtos = models.ManyToManyField("loja.Produto", verbose_name="produtos", blank=True,
                                      related_name="regras_servico")
    categorias = models.ManyToManyField("loja.Categoria", verbose_name="categorias", blank=True,
                                        related_name="regras_servico")
    preco_de = models.DecimalField(
        "preco do produto a partir de", max_digits=12, decimal_places=2, null=True,
        blank=True, validators=NAO_NEGATIVO)
    preco_ate = models.DecimalField(
        "preco do produto ate", max_digits=12, decimal_places=2, null=True, blank=True,
        validators=NAO_NEGATIVO,
        help_text="Faixa pelo preco da variante padrao do produto.")
    preco = models.DecimalField(
        "preco do servico", max_digits=12, decimal_places=2, null=True, blank=True,
        validators=NAO_NEGATIVO,
        help_text="Vazio: vale o preco padrao do servico.")

    class Meta:
        verbose_name = "regra do servico"
        verbose_name_plural = "regras do servico"
        ordering = ["servico", "ordem", "pk"]

    def __str__(self):
        return f"{self.servico} #{self.ordem}"

    def clean(self):
        super().clean()
        if None not in (self.preco_de, self.preco_ate) and self.preco_de > self.preco_ate:
            raise ValidationError({"preco_ate": "O minimo da faixa passa do maximo."})

    def validar_criterios(self, produtos, categorias, preco_de=None, preco_ate=None):
        """Produtos e categorias so existem no form (M2M): quem salva chama aqui."""
        faixa = (preco_de, preco_ate) if (preco_de, preco_ate) != (None, None) else (
            self.preco_de, self.preco_ate)
        if not (produtos or categorias) and faixa == (None, None):
            raise ValidationError(
                "Escolha produtos, categorias ou uma faixa de preco: regra vazia valeria "
                "para o catalogo inteiro.")
