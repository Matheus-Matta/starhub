from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from .base import NAO_NEGATIVO, ComDatas, JSONDecimalField


def sku_do_servico(nome):
    """SKU que o servico ganha ao nascer sozinho: "Montagem" -> "SERV-MONTAGEM"."""
    return f"SERV-{slugify(nome).upper()}"[:100]


class CategoriaServico(ComDatas):
    """Grupo de servicos que o cliente escolhe junto, um de cada grupo.

    No Suri cada categoria vira um atributo da variacao, nesta ordem: "Instalação"
    (Simples ou Completa) e abaixo "Impermeabilização" (Sem serviço ou Imper).
    """

    nome = models.CharField("nome", max_length=100,
                            help_text="Vira o nome do atributo no Suri.")
    ordem = models.PositiveIntegerField(
        "ordem", default=10, help_text="Menor primeiro: a ordem dos atributos no Suri.")

    class Meta:
        verbose_name = "categoria de servico"
        verbose_name_plural = "categorias de servico"
        ordering = ["ordem", "nome"]
        constraints = [models.UniqueConstraint(fields=["account", "nome"],
                                               name="categoria_servico_nome_conta_unico")]

    def __str__(self):
        return self.nome


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
    categoria = models.ForeignKey(
        CategoriaServico, verbose_name="categoria", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="servicos",
        help_text="Com um servico so na categoria, o Suri oferece \"Sem serviço\"; com "
                  "dois ou mais, o cliente escolhe um. Sem categoria: atributo Serviço.")
    # {"src", "alt"}, como a imagem da categoria: vai como foto da variacao no Suri.
    imagem = JSONDecimalField("imagem", null=True, blank=True)

    class Inclusao(models.TextChoices):
        ESCOLHA = "escolha", "So quando o cliente escolhe"
        REGRA = "regra", "Sempre, nos produtos das regras"
        TODOS = "todos", "Sempre, em todo item do pedido"

    inclusao = models.CharField(
        "incluir no pedido", max_length=10, choices=Inclusao, default=Inclusao.ESCOLHA,
        help_text="Sempre: o pedido que chega das lojas ganha o servico em cada item, com o "
                  "preco da regra (ou o padrao), sem mudar o total que o cliente pagou.")
    # So as integracoes que oferecem o servico ao cliente: o WooCommerce nao recebe
    # servico como produto, so dentro do pedido (pedido legado).
    INTEGRACOES = [("shopify", "Shopify"), ("suri", "Suri Shop")]
    fora_das_integracoes = models.JSONField(
        "ignorar nas integracoes", default=list, blank=True,
        help_text="Nas escolhidas o servico nao vira variacao (Suri) nem aparece no tema "
                  "(Shopify). Use com Sempre para o servico que o cliente nao escolhe.")

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

    def ignorado_em(self, plataforma):
        return plataforma in (self.fora_das_integracoes or [])


class RegraServico(ComDatas):
    """A quais produtos o servico vale e por qual preco (uma regra por linha).

    A regra e de um tipo so: por categoria (as categorias escolhidas, com faixa de
    preco opcional) ou por produto (os produtos escolhidos, um por linha). Para cada
    produto vale a primeira regra ativa que casa, pela ordem (menor primeiro); e ela
    que da o preco. Regras em apps/loja/services/servicos_regras.py.
    """

    class Tipo(models.TextChoices):
        CATEGORIA = "categoria", "Por categoria"
        PRODUTO = "produto", "Por produto"

    servico = models.ForeignKey(Servico, verbose_name="servico", on_delete=models.CASCADE,
                                related_name="regras")
    tipo = models.CharField("tipo", max_length=20, choices=Tipo, default=Tipo.CATEGORIA)
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
        help_text="Faixa pelo preco da variante padrao, dentro das categorias.")
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

    def validar_criterios(self, produtos, categorias):
        """Produtos e categorias vem das linhas do form (inline): quem salva chama aqui."""
        if self.tipo == self.Tipo.PRODUTO and not produtos:
            raise ValidationError("Adicione ao menos um produto: regra por produto sem "
                                  "produto nao vale para nenhum.")
        if self.tipo == self.Tipo.CATEGORIA and not categorias:
            raise ValidationError("Adicione ao menos uma categoria: regra por categoria sem "
                                  "categoria valeria para o catalogo inteiro.")
