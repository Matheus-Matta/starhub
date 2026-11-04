from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel


class ApresentacaoServicoShopify(BaseModel):
    """Como um servico aparece no bloco da pagina de produto da Shopify."""

    class TipoCampo(models.TextChoices):
        CHECKBOX = "checkbox", "Checkbox"
        RADIO = "radio", "Radio"
        LISTA = "select", "Lista"
        CARTOES = "cards", "Cartoes"

    class Padrao(models.TextChoices):
        NENHUM = "none", "Nenhum"
        PRINCIPAL = "principal", "Este servico"
        ALTERNATIVO = "alternativo", "Servico vinculado"

    servico = models.OneToOneField(
        "loja.Servico", verbose_name="servico", on_delete=models.CASCADE,
        related_name="apresentacao_shopify",
    )
    tipo_campo = models.CharField(
        "tipo do campo", max_length=10, choices=TipoCampo, default=TipoCampo.CHECKBOX)
    rotulo = models.CharField(
        "rotulo", max_length=150, blank=True,
        help_text="Vazio usa o nome do servico.")
    descricao = models.CharField(
        "descricao", max_length=255, blank=True,
        help_text="Texto curto mostrado abaixo da opcao.")
    ordem = models.PositiveIntegerField(
        "ordem", default=10, help_text="Menor aparece primeiro.")
    servicos_vinculados = models.ManyToManyField(
        "loja.Servico", verbose_name="servicos vinculados", blank=True,
        related_name="apresentacoes_shopify_vinculadas",
        help_text="No Radio, Lista ou Cartoes, cria uma escolha entre varios servicos.")
    titulo_grupo = models.CharField(
        "titulo do grupo", max_length=150, blank=True,
        help_text="Exemplo: Escolha o tipo de garantia.")
    obrigatorio = models.BooleanField(
        "escolha obrigatoria", default=False,
        help_text="Impede adicionar ao carrinho sem escolher uma opcao do grupo.")
    padrao = models.CharField(
        "opcao inicial", max_length=12, choices=Padrao, default=Padrao.NENHUM,
        help_text="Servico vinculado seleciona o primeiro da lista exibida.")

    class Meta:
        verbose_name = "apresentacao de servico na Shopify"
        verbose_name_plural = "apresentacoes de servicos na Shopify"
        ordering = ["ordem", "servico__nome"]

    def __str__(self):
        return f"{self.servico} na Shopify"

    def validar_vinculados(self, vinculados):
        vinculados = list(vinculados)
        exclusivo = self.tipo_campo in (self.TipoCampo.RADIO, self.TipoCampo.LISTA)
        if exclusivo and not vinculados:
            raise ValidationError({"servicos_vinculados": "Escolha o servico vinculado."})
        if self.servico_id and any(item.pk == self.servico_id for item in vinculados):
            raise ValidationError({"servicos_vinculados": "Escolha outro servico."})
        if self.padrao == self.Padrao.ALTERNATIVO and not vinculados:
            raise ValidationError({"padrao": "A opcao vinculada exige um servico vinculado."})

    def clean(self):
        super().clean()
        if self.pk:
            self.validar_vinculados(self.servicos_vinculados.all())
