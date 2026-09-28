from django.core.validators import MinValueValidator
from django.db import models

from apps.core.services.rules import validate_rules

from .base import BaseModel
from .shared import ExternalReference, SalesChannel


class PublicationPolicy(BaseModel):
    class EntityType(models.TextChoices):
        PRODUCT = "product", "Produto"
        ORDER = "order", "Pedido"
        COUPON = "coupon", "Cupom"
        CUSTOMER = "customer", "Cliente"

    class DefaultAction(models.TextChoices):
        ALLOW = "allow", "Permitir"
        DENY = "deny", "Negar"

    name = models.CharField("nome", max_length=150)
    entity_type = models.CharField("tipo de entidade", max_length=20, choices=EntityType)
    target_channel = models.ForeignKey(
        SalesChannel, verbose_name="canal de destino", on_delete=models.PROTECT
    )
    enabled = models.BooleanField("habilitada", default=True)
    priority = models.PositiveIntegerField(
        "prioridade", default=0, validators=[MinValueValidator(0)]
    )
    default_action = models.CharField("acao padrao", max_length=10, choices=DefaultAction)
    rules = models.JSONField("regras", default=dict, blank=True, validators=[validate_rules])

    class Meta:
        verbose_name = "politica de publicacao"
        verbose_name_plural = "politicas de publicacao"


class PublicationState(BaseModel):
    class DesiredState(models.TextChoices):
        PUBLISHED = "published", "Publicado"
        UNPUBLISHED = "unpublished", "Nao publicado"

    class SyncStatus(models.TextChoices):
        PENDING = "pending", "Pendente"
        SYNCING = "syncing", "Sincronizando"
        SYNCED = "synced", "Sincronizado"
        FAILED = "failed", "Falhou"
        SKIPPED = "skipped", "Ignorado"
        UNSUPPORTED = "unsupported", "Nao suportado"

    entity_type = models.CharField(
        "tipo de entidade", max_length=20, choices=PublicationPolicy.EntityType
    )
    object_id = models.CharField("id interno", max_length=64)
    channel = models.ForeignKey(SalesChannel, verbose_name="canal", on_delete=models.PROTECT)
    desired_state = models.CharField("estado desejado", max_length=20, choices=DesiredState)
    sync_status = models.CharField(
        "status da sincronizacao", max_length=20, choices=SyncStatus, default=SyncStatus.PENDING
    )
    external_reference = models.ForeignKey(
        ExternalReference, verbose_name="referencia externa", null=True, blank=True,
        on_delete=models.SET_NULL
    )
    last_synced_at = models.DateTimeField("ultima sincronizacao", null=True, blank=True)
    last_error = models.TextField("ultimo erro", blank=True)
    payload_hash = models.CharField("hash do conteudo", max_length=64, blank=True)

    class Meta:
        verbose_name = "estado de publicacao"
        verbose_name_plural = "estados de publicacao"
        constraints = [models.UniqueConstraint(
            fields=["account", "entity_type", "object_id", "channel"],
            name="publicacao_objeto_canal_unica",
        )]
