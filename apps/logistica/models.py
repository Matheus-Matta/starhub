from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q

from apps.core.models import BaseModel

CEP = RegexValidator(r"^\d{8}$", "Informe o CEP com 8 digitos, por exemplo 01001-000.")
NAO_NEGATIVO = [MinValueValidator(0)]


def _dinheiro(rotulo, **extra):
    return models.DecimalField(rotulo, max_digits=12, decimal_places=2,
                               validators=NAO_NEGATIVO, **extra)


class TabelaFrete(BaseModel):
    """Uma forma de cobrar o frete: por distancia (km) ou por faixa de CEP.

    So o cadastro e a cotacao (apps/logistica/cotacao.py); ainda nao ligada a pedido
    nem a checkout.
    """

    class Tipo(models.TextChoices):
        DISTANCIA = "distancia", "Por distancia (km)"
        FAIXA_CEP = "faixa_cep", "Por faixa de CEP"

    nome = models.CharField("nome", max_length=150)
    tipo = models.CharField("forma de cobranca", max_length=20, choices=Tipo,
                            default=Tipo.DISTANCIA)
    prazo_dias = models.PositiveSmallIntegerField(
        "prazo (dias uteis)", default=0,
        help_text="Por distancia: prazo de toda entrega. Por faixa: vale para a faixa sem prazo.")
    no_checkout = models.BooleanField(
        "oferecer no checkout das lojas", default=False,
        help_text="Vira opcao de frete com o nome desta tabela: Shopify (cotacao na hora), "
                  "WooCommerce (zonas de entrega, so faixa de CEP) e Suri (orcamento), "
                  "nas lojas com o frete ligado.")
    # Por distancia.
    cep_origem = models.CharField("CEP de origem", max_length=8, blank=True, validators=[CEP],
                                  help_text="De onde a entrega sai (deposito ou loja).")
    preco_por_km = _dinheiro("preco por km", null=True, blank=True)
    taxa_fixa = _dinheiro("taxa fixa", default=0,
                          help_text="Somada a toda entrega, alem do valor por km.")
    valor_minimo = _dinheiro("valor minimo", default=0,
                             help_text="Entrega perto nunca sai por menos que isto.")
    distancia_maxima_km = models.DecimalField(
        "distancia maxima (km)", max_digits=8, decimal_places=1, null=True, blank=True,
        validators=NAO_NEGATIVO, help_text="Acima disto nao entrega. Vazio = sem limite.")

    class Meta:
        verbose_name = "tabela de frete"
        verbose_name_plural = "tabelas de frete"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        # O formulario esconde os campos de distancia na faixa de CEP (so visual): a
        # obrigatoriedade de cada forma e conferida aqui, com o erro no campo.
        if self.tipo == self.Tipo.DISTANCIA:
            erros = {}
            if not self.cep_origem:
                erros["cep_origem"] = "Informe o CEP de onde a entrega sai."
            if self.preco_por_km is None:
                erros["preco_por_km"] = "Informe quanto custa cada km."
            if erros:
                raise ValidationError(erros)


class FaixaCep(BaseModel):
    tabela = models.ForeignKey(TabelaFrete, verbose_name="tabela", on_delete=models.CASCADE,
                               related_name="faixas")
    cep_inicial = models.CharField("CEP inicial", max_length=8, validators=[CEP])
    cep_final = models.CharField("CEP final", max_length=8, validators=[CEP])
    valor = _dinheiro("valor")
    prazo_dias = models.PositiveSmallIntegerField(
        "prazo (dias uteis)", null=True, blank=True, help_text="Vazio = prazo da tabela.")

    class Meta:
        verbose_name = "faixa de CEP"
        verbose_name_plural = "faixas de CEP"
        ordering = ["cep_inicial"]
        constraints = [
            # CEP com 8 digitos ordena como texto igual a como numero.
            models.CheckConstraint(condition=Q(cep_inicial__lte=F("cep_final")),
                                   name="faixa_cep_inicial_ate_final"),
        ]

    def __str__(self):
        return f"{self.cep_inicial} a {self.cep_final}"

    def clean(self):
        super().clean()
        if self.cep_inicial and self.cep_final and self.cep_inicial > self.cep_final:
            raise ValidationError({"cep_final": "O CEP final tem que ser maior que o inicial."})


class CoordenadaCep(models.Model):
    """Latitude e longitude de um CEP, consultadas uma vez so (APIs gratuitas tem limite).

    Dado publico, igual para todas as contas: nao e por conta (BaseModel).
    """

    cep = models.CharField("CEP", max_length=8, unique=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    fonte = models.CharField("fonte", max_length=30)
    consultado_em = models.DateTimeField("consultado em", auto_now=True)

    class Meta:
        verbose_name = "coordenada de CEP"
        verbose_name_plural = "coordenadas de CEP"

    def __str__(self):
        return f"{self.cep} ({self.latitude}, {self.longitude})"


class DistanciaCep(models.Model):
    """Km por estrada entre dois CEPs, guardado: o checkout da Shopify espera so 3 s.

    So a distancia da rota (OSRM) e guardada; a estimativa em linha reta nao, para a
    proxima cotacao tentar a rota de novo.
    """

    origem = models.CharField("CEP de origem", max_length=8)
    destino = models.CharField("CEP de destino", max_length=8)
    km = models.DecimalField(max_digits=8, decimal_places=1)
    consultado_em = models.DateTimeField("consultado em", auto_now=True)

    class Meta:
        verbose_name = "distancia entre CEPs"
        verbose_name_plural = "distancias entre CEPs"
        constraints = [models.UniqueConstraint(fields=["origem", "destino"],
                                               name="distancia_cep_unica")]

    def __str__(self):
        return f"{self.origem} -> {self.destino}: {self.km} km"
