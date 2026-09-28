import re

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.validators import validar_documento, validar_telefone, validar_uf

from .base import BaseModel, Origin


class Address(BaseModel):
    name = models.CharField("nome", max_length=100, blank=True)
    company = models.CharField("empresa", max_length=150, blank=True)
    recipient_name = models.CharField("destinatario", max_length=150, blank=True)
    phone = models.CharField("telefone", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    address_line_1 = models.CharField("endereco", max_length=200, blank=True)
    address_line_2 = models.CharField("endereco complementar", max_length=200, blank=True)
    number = models.CharField("numero", max_length=30, blank=True)
    complement = models.CharField("complemento", max_length=100, blank=True)
    neighborhood = models.CharField("bairro", max_length=100, blank=True)
    city = models.CharField("cidade", max_length=100, blank=True)
    state = models.CharField("estado", max_length=100, blank=True)
    state_code = models.CharField("UF", max_length=10, blank=True)
    postal_code = models.CharField("CEP", max_length=20, blank=True)
    country = models.CharField("pais", max_length=100, blank=True)
    country_code = models.CharField("codigo do pais", max_length=2, blank=True)
    reference = models.CharField("referencia", max_length=200, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    document = models.CharField("documento", max_length=30, blank=True)
    is_default = models.BooleanField("padrao", default=False)
    metadata = models.JSONField("metadados", default=dict, blank=True)

    class Meta:
        verbose_name = "endereco"
        verbose_name_plural = "enderecos"

    def clean(self):
        super().clean()
        erros = {}
        pais = self.country_code.strip().upper()
        cep = "".join(char for char in self.postal_code if char.isalnum())
        # So o endereco brasileiro tem CEP e UF de formato fixo; o estrangeiro passa livre.
        if pais == "BR" and cep and not re.fullmatch(r"\d{8}", cep):
            erros["postal_code"] = "CEP invalido: use 8 digitos (ex.: 50030-230)."
        if pais and not re.fullmatch(r"[A-Z]{2}", pais):
            erros["country_code"] = "Use a sigla de 2 letras do pais, ex.: BR."
        validacoes = [("phone", validar_telefone), ("document", validar_documento)]
        if pais == "BR":
            validacoes.append(("state_code", validar_uf))
        for campo, validar in validacoes:
            try:
                validar(getattr(self, campo))
            except ValidationError as erro:
                erros[campo] = erro.messages
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        self.country_code = self.country_code.strip().upper()
        self.state_code = self.state_code.strip().upper()
        self.postal_code = "".join(char for char in self.postal_code if char.isalnum()).upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name or self.recipient_name or self.address_line_1 or "Endereco"


class ExternalReference(BaseModel):
    platform = models.CharField("plataforma", max_length=30, choices=Origin.choices)
    entity_type = models.CharField("tipo de entidade", max_length=50)
    object_id = models.CharField("id interno", max_length=64)
    external_id = models.CharField("id externo", max_length=255)
    external_parent_id = models.CharField("id externo pai", max_length=255, blank=True)
    metadata = models.JSONField("metadados", default=dict, blank=True)

    class Meta:
        verbose_name = "referencia externa"
        verbose_name_plural = "referencias externas"
        constraints = [models.UniqueConstraint(
            fields=["account", "platform", "entity_type", "external_id"],
            name="referencia_externa_unica",
        )]


class SalesChannel(BaseModel):
    name = models.CharField("nome", max_length=150)
    platform = models.CharField("plataforma", max_length=30, choices=Origin.choices)
    external_store_id = models.CharField("id externo da loja", max_length=255, blank=True)
    settings = models.JSONField("configuracoes", default=dict, blank=True)

    class Meta:
        verbose_name = "canal de venda"
        verbose_name_plural = "canais de venda"
        constraints = [models.UniqueConstraint(
            fields=["account", "platform", "external_store_id"],
            name="canal_externo_conta_unico",
        )]

    def __str__(self):
        return self.name
