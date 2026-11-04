from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel

CAMPOS = [
    ("cliente.nome", "Cliente: nome"),
    ("cliente.sobrenome", "Cliente: sobrenome"),
    ("cliente.nome_completo", "Cliente: nome completo"),
    ("cliente.email", "Cliente: e-mail"),
    ("cliente.telefone", "Cliente: telefone"),
    ("cliente.cpf", "Cliente: CPF"),
    ("cliente.cnpj", "Cliente: CNPJ"),
    ("cliente.empresa", "Cliente: empresa"),
    ("cliente.nascimento", "Cliente: nascimento"),
    ("cliente.aceita_marketing", "Cliente: aceita marketing"),
    ("cliente.cliente_pagante", "Cliente: ja pagou"),
    ("pedido.numero", "Pedido: numero"),
    ("pedido.status", "Pedido: status"),
    ("pedido.status_pagamento", "Pedido: status do pagamento"),
    ("pedido.status_entrega", "Pedido: status da entrega"),
    ("pedido.total", "Pedido: total"),
    ("pedido.forma_pagamento", "Pedido: forma de pagamento"),
    ("pedido.metodo_envio", "Pedido: metodo de envio"),
    ("pedido.canal_origem", "Pedido: canal de origem"),
]


class RegraEnvio(BaseModel):
    class Operador(models.TextChoices):
        IGUAL = "eq", "igual a"
        DIFERENTE = "neq", "diferente de"
        CONTEM = "contains", "contem"
        NAO_CONTEM = "not_contains", "nao contem"
        MAIOR = "gt", "maior que"
        MAIOR_IGUAL = "gte", "maior ou igual a"
        MENOR = "lt", "menor que"
        MENOR_IGUAL = "lte", "menor ou igual a"
        VAZIO = "is_null", "esta vazio"
        PREENCHIDO = "is_not_null", "esta preenchido"

    conjunto = models.ForeignKey(
        "starchats.ConjuntoEnvio",
        on_delete=models.CASCADE,
        related_name="regras",
        null=True,
        blank=True,
    )
    nome = models.CharField(max_length=150)
    campo = models.CharField(max_length=50, choices=CAMPOS)
    operador = models.CharField(max_length=20, choices=Operador)
    valor = models.CharField(
        max_length=255,
        blank=True,
        help_text="Ex.: confirmed, true ou 100.00. Vazio nos operadores de vazio.",
    )

    class Meta:
        verbose_name = "regra de envio"
        verbose_name_plural = "Regras de envio"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        if not self.conjunto_id:
            raise ValidationError({"conjunto": "Cadastre a regra dentro de um conjunto."})
        sem_valor = {self.Operador.VAZIO, self.Operador.PREENCHIDO}
        if self.operador not in sem_valor and not self.valor.strip():
            raise ValidationError({"valor": "Informe o valor comparado por esta regra."})
        if self.operador in sem_valor:
            return
        if self.campo in {"cliente.aceita_marketing", "cliente.cliente_pagante"}:
            if self.valor.casefold() not in {"true", "false", "sim", "nao", "1", "0"}:
                raise ValidationError({"valor": "Use true/false, sim/nao ou 1/0."})
        if self.campo == "pedido.total":
            try:
                Decimal(self.valor.replace(",", "."))
            except InvalidOperation as erro:
                mensagem = {"valor": "Informe um valor numerico, como 100.00."}
                raise ValidationError(mensagem) from erro
