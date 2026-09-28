from django.core.validators import MinValueValidator
from django.db import models

from .base import NAO_NEGATIVO, ComDatas, JSONDecimalField


class PagamentoPedido(ComDatas):
    class Status(models.TextChoices):
        PENDENTE = "pending", "Pendente"
        AUTORIZADO = "authorized", "Autorizado"
        PAGO = "paid", "Pago"
        REEMBOLSADO = "refunded", "Reembolsado"
        ESTORNADO = "voided", "Estornado"
        FALHOU = "failed", "Falhou"

    pedido = models.ForeignKey(
        "loja.Pedido", verbose_name="pedido", on_delete=models.CASCADE, related_name="pagamentos"
    )
    provider = models.CharField("provedor", max_length=100)
    transaction_id = models.CharField("id da transacao", max_length=255, blank=True)
    status = models.CharField("status", max_length=20, choices=Status, default=Status.PENDENTE)
    amount = models.DecimalField("valor", max_digits=12, decimal_places=2, validators=NAO_NEGATIVO)
    currency = models.CharField("moeda", max_length=3, default="BRL")
    installments = models.PositiveIntegerField(
        "parcelas", default=1, validators=[MinValueValidator(1)]
    )
    paid_at = models.DateTimeField("pago em", null=True, blank=True)
    metadata = JSONDecimalField("dados extras", default=dict, blank=True)

    class Meta:
        verbose_name = "pagamento"
        verbose_name_plural = "pagamentos"
        ordering = ["id"]

    def __str__(self):
        return f"{self.provider} {self.transaction_id}".strip()


class EntregaPedido(ComDatas):
    class Status(models.TextChoices):
        PENDENTE = "pending", "Pendente"
        EM_TRANSITO = "in_transit", "Em transito"
        ENTREGUE = "delivered", "Entregue"
        DEVOLVIDO = "returned", "Devolvido"

    pedido = models.ForeignKey(
        "loja.Pedido", verbose_name="pedido", on_delete=models.CASCADE, related_name="entregas"
    )
    status = models.CharField("status", max_length=20, choices=Status, default=Status.PENDENTE)
    tracking_company = models.CharField("transportadora", max_length=100, blank=True)
    tracking_number = models.CharField("codigo de rastreio", max_length=100, blank=True)
    tracking_url = models.URLField("link de rastreio", blank=True)
    shipped_at = models.DateTimeField("enviado em", null=True, blank=True)
    delivered_at = models.DateTimeField("entregue em", null=True, blank=True)
    metadata = JSONDecimalField("dados extras", default=dict, blank=True)

    class Meta:
        verbose_name = "entrega"
        verbose_name_plural = "entregas"
        ordering = ["id"]

    def __str__(self):
        return self.tracking_number or self.get_status_display()
