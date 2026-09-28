from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import Address
from apps.core.tenant.validators import conta_do_registro, validate_same_account
from apps.loja.validators import (
    normalizar_telefone,
    somente_digitos,
    validar_cnpj,
    validar_cpf,
    validar_telefone,
)

from .base import ComDatas


class Cliente(ComDatas):
    class TipoDocumento(models.TextChoices):
        CPF = "cpf", "CPF"
        CNPJ = "cnpj", "CNPJ"
        OUTRO = "other", "Outro"

    email = models.EmailField("e-mail")
    email_normalizado = models.EmailField(editable=False)
    nome = models.CharField("nome", max_length=150, blank=True)
    sobrenome = models.CharField("sobrenome", max_length=150, blank=True)
    telefone = models.CharField("telefone", max_length=20, blank=True)
    cpf = models.CharField("CPF", max_length=11, blank=True)
    cnpj = models.CharField("CNPJ", max_length=14, blank=True)
    tipo_documento = models.CharField(
        "tipo de documento", max_length=10, choices=TipoDocumento, blank=True
    )
    empresa = models.CharField("empresa", max_length=150, blank=True)
    nascimento = models.DateField("nascimento", null=True, blank=True)
    notas = models.TextField("notas", blank=True)
    aceita_marketing = models.BooleanField("aceita marketing", default=False)
    isento_imposto = models.BooleanField("isento de imposto", default=False)
    locale = models.CharField("idioma", max_length=10, default="pt-BR")
    usuario = models.CharField("usuario", max_length=150, blank=True)
    papel = models.CharField("papel", max_length=50, default="customer")
    cliente_pagante = models.BooleanField("ja pagou algum pedido", default=False)
    avatar_url = models.URLField("avatar", blank=True)
    enderecos = models.ManyToManyField(Address, through="ClienteEndereco", blank=True)

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["nome", "sobrenome"]
        constraints = [
            models.UniqueConstraint(
                fields=["account", "email_normalizado"], name="cliente_email_conta_unico"
            ),
            models.UniqueConstraint(
                fields=["account", "cpf"], condition=~Q(cpf=""), name="cliente_cpf_conta_unico"
            ),
        ]

    def __str__(self):
        return self.nome_completo or self.email

    @property
    def nome_completo(self):
        return f"{self.nome} {self.sobrenome}".strip()

    def clean(self):
        # O indice unico barra no banco; aqui o erro vira mensagem no campo certo.
        super().clean()
        erros = {}
        email = (self.email or "").strip().casefold()
        # Filtro explicito pela conta: o superusuario no admin enxerga todas.
        mesma_conta = Cliente.objects.filter(account_id=conta_do_registro(self))
        if email and mesma_conta.filter(email_normalizado=email).exclude(pk=self.pk).exists():
            erros["email"] = "Ja existe um cliente com este e-mail."
        validacoes = (("cpf", validar_cpf), ("cnpj", validar_cnpj), ("telefone", validar_telefone))
        for campo, validar in validacoes:
            try:
                validar(getattr(self, campo))
            except ValidationError as erro:
                erros[campo] = erro.messages
        # Escolheu o tipo do documento: o documento daquele tipo passa a ser obrigatorio.
        for tipo, campo in ((self.TipoDocumento.CPF, "cpf"), (self.TipoDocumento.CNPJ, "cnpj")):
            if self.tipo_documento == tipo and not getattr(self, campo) and campo not in erros:
                nome = campo.upper()
                erros[campo] = f"Informe o {nome}: o tipo de documento escolhido e {nome}."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        self.email_normalizado = self.email.casefold()
        self.cpf = somente_digitos(self.cpf)
        self.cnpj = somente_digitos(self.cnpj)
        validar_cpf(self.cpf)
        self.telefone = normalizar_telefone(self.telefone)
        if not self.usuario:
            self.usuario = self.email.split("@")[0]
        super().save(*args, **kwargs)


class ClienteEndereco(ComDatas):
    class Tipo(models.TextChoices):
        COBRANCA = "billing", "Cobranca"
        ENTREGA = "shipping", "Entrega"
        OUTRO = "other", "Outro"

    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="vinculos_endereco")
    endereco = models.ForeignKey(Address, on_delete=models.CASCADE, related_name="clientes")
    tipo = models.CharField(max_length=10, choices=Tipo, default=Tipo.OUTRO)
    padrao = models.BooleanField(default=False)

    class Meta:
        verbose_name = "endereco do cliente"
        verbose_name_plural = "enderecos do cliente"
        constraints = [models.UniqueConstraint(
            fields=["account", "cliente", "endereco", "tipo"],
            name="cliente_endereco_tipo_unico",
        )]

    def clean(self):
        validate_same_account(self, self.cliente, self.endereco)
