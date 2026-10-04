"""Opcoes de variante: tipo (Cor), valor (Preto) e o valor escolhido em cada variante."""

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.tenant.validators import validate_same_account

from .base import ComDatas


class TipoVariante(ComDatas):
    """Tipo de opcao global da conta (Cor, Tamanho, Voltagem): cadastrado uma vez e
    usado por qualquer produto. Cada variante escolhe o tipo e o valor dela
    (ValorDaVarianteProduto): a Cor tem 20 cores, a camiseta usa 2."""

    nome = models.CharField("nome", max_length=100)
    posicao = models.PositiveIntegerField("posicao", default=0)

    class Meta:
        verbose_name = "tipo de variante"
        verbose_name_plural = "tipos de variante"
        ordering = ["posicao", "id"]
        constraints = [models.UniqueConstraint(
            fields=["account", "nome"], name="tipo_variante_nome_conta"
        )]

    def __str__(self):
        return self.nome


class ValorVariante(ComDatas):
    tipo = models.ForeignKey(
        TipoVariante, verbose_name="tipo", on_delete=models.CASCADE, related_name="valores"
    )
    valor = models.CharField("valor", max_length=100)
    valor_normalizado = models.CharField(max_length=100, editable=False)
    posicao = models.PositiveIntegerField("posicao", default=0)

    class Meta:
        verbose_name = "valor de variante"
        verbose_name_plural = "valores de variante"
        ordering = ["posicao", "id"]
        constraints = [models.UniqueConstraint(
            fields=["account", "tipo", "valor_normalizado"], name="valor_variante_tipo_unico"
        )]

    def __str__(self):
        return f"{self.tipo.nome}: {self.valor}"

    def save(self, *args, **kwargs):
        self.valor = self.valor.strip()
        self.valor_normalizado = self.valor.casefold()
        super().save(*args, **kwargs)


class ValorDaVarianteProduto(ComDatas):
    variante = models.ForeignKey(
        "loja.VarianteProduto", verbose_name="variante", on_delete=models.CASCADE,
        related_name="opcoes"
    )
    valor = models.ForeignKey(
        ValorVariante, verbose_name="valor", on_delete=models.CASCADE, related_name="variantes"
    )

    class Meta:
        verbose_name = "valor da variante"
        verbose_name_plural = "valores da variante"
        constraints = [models.UniqueConstraint(
            fields=["variante", "valor"], name="variante_valor_unico"
        )]

    def clean(self):
        validate_same_account(self, self.variante, self.valor)
        if self.variante.pk is None:
            # Variante nova (salva junto): nada no banco para conflitar; duas linhas
            # novas do mesmo tipo o OpcoesFormSet do admin ja barra.
            return
        conflito = type(self).objects.filter(
            variante=self.variante, valor__tipo=self.valor.tipo
        ).exclude(pk=self.pk)
        if conflito.exists():
            raise ValidationError("A variante ja possui um valor para este tipo.")
