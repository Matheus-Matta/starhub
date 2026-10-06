import uuid

from django.core.exceptions import ValidationError
from django.core.validators import DomainNameValidator
from django.db import models
from simple_history.models import HistoricalRecords

from apps.core.tenant.context import usuario_do_historico
from apps.core.validators import validar_documento, validar_telefone


class Account(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("nome", max_length=150)
    slug = models.SlugField("slug", max_length=150, unique=True)
    legal_name = models.CharField("razao social", max_length=200, blank=True)
    document = models.CharField("documento", max_length=30, blank=True)
    email = models.EmailField("e-mail", blank=True)
    phone = models.CharField("telefone", max_length=30, blank=True)
    dominio_avaliacoes = models.CharField(
        "dominio da loja para avaliacoes", max_length=253, blank=True,
        validators=[DomainNameValidator(accept_idna=False)],
        help_text="Ex.: maxxxmoveis.com.br. Informe o dominio exato, sem https:// ou caminho.",
    )
    timezone = models.CharField("fuso horario", max_length=50, default="America/Sao_Paulo")
    currency = models.CharField("moeda", max_length=3, default="BRL")
    active = models.BooleanField("ativa", default=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("alterada em", auto_now=True)
    historical = HistoricalRecords(get_user=usuario_do_historico)

    class Meta:
        verbose_name = "conta"
        verbose_name_plural = "contas"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        erros = {}
        for campo, validar in (("document", validar_documento), ("phone", validar_telefone)):
            try:
                validar(getattr(self, campo))
            except ValidationError as erro:
                erros[campo] = erro.messages
        if self.currency and not (len(self.currency) == 3 and self.currency.isalpha()):
            erros["currency"] = "Use o codigo de 3 letras da moeda, ex.: BRL."
        if erros:
            raise ValidationError(erros)
