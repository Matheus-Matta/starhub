from django.db import models

from .base import ComDatas, JSONDecimalField


class Categoria(ComDatas):
    class Exibicao(models.TextChoices):
        PADRAO = "default", "Padrao"
        PRODUTOS = "products", "Produtos"
        SUBCATEGORIAS = "subcategories", "Subcategorias"
        AMBOS = "both", "Ambos"

    nome = models.CharField("nome", max_length=200)
    slug = models.SlugField("slug", max_length=200, allow_unicode=True)
    pai = models.ForeignKey(
        "self", verbose_name="categoria pai", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="filhas",
    )
    descricao = models.TextField("descricao", blank=True)
    exibicao = models.CharField("exibicao", max_length=20, choices=Exibicao, default="default")
    imagem = JSONDecimalField("imagem", null=True, blank=True)
    ordem = models.IntegerField("ordem", default=0)

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["ordem", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["account", "slug"], name="categoria_slug_conta"),
        ]

    def __str__(self):
        return self.nome
