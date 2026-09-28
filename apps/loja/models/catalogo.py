from django.db import models
from django.utils.text import slugify

from .base import ComDatas


class Tag(ComDatas):
    nome = models.CharField("nome", max_length=100)
    nome_normalizado = models.CharField(max_length=100, editable=False)
    slug = models.SlugField(max_length=120)

    class Meta:
        verbose_name = "tag"
        verbose_name_plural = "tags"
        ordering = ["nome"]
        constraints = [models.UniqueConstraint(
            fields=["account", "nome_normalizado"], name="tag_nome_conta_unico"
        )]

    def save(self, *args, **kwargs):
        self.nome = self.nome.strip()
        self.nome_normalizado = self.nome.casefold()
        self.slug = self.slug or slugify(self.nome)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome


class MidiaProduto(ComDatas):
    class Tipo(models.TextChoices):
        IMAGEM = "image", "Imagem"
        VIDEO = "video", "Video"
        MODELO = "model", "Modelo 3D"

    produto = models.ForeignKey("loja.Produto", on_delete=models.CASCADE, related_name="midias")
    variante = models.ForeignKey(
        "loja.VarianteProduto", null=True, blank=True,
        on_delete=models.CASCADE, related_name="midias",
    )
    url = models.URLField("URL", max_length=500)
    alt_text = models.CharField("texto alternativo", max_length=255, blank=True)
    posicao = models.PositiveIntegerField(default=0)
    tipo = models.CharField(max_length=10, choices=Tipo, default=Tipo.IMAGEM)

    class Meta:
        verbose_name = "midia do produto"
        verbose_name_plural = "midias do produto"
        ordering = ["posicao", "id"]
