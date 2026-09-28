from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from apps.core.tenant.context import (
    get_current_account_id,
    get_current_user,
    usuario_do_historico,
    ve_todas_as_contas,
)
from apps.core.tenant.exceptions import TenantMismatchError
from apps.core.tenant.managers import TenantManager, UnscopedManager
from apps.core.tenant.validators import conta_herdada, validate_model_relations


class Origin(models.TextChoices):
    STARHUB = "starhub", "StarHub"
    SHOPIFY = "shopify", "Shopify"
    WOOCOMMERCE = "woocommerce", "WooCommerce"
    MERCADO_LIVRE = "mercado_livre", "Mercado Livre"
    SHOPEE = "shopee", "Shopee"
    AMAZON = "amazon", "Amazon"
    MAGALU = "magalu", "Magalu"
    API = "api", "API"
    IMPORT = "import", "Importacao"


class BaseModel(models.Model):
    account = models.ForeignKey(
        "core.Account", verbose_name="conta", on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
    )
    active = models.BooleanField("ativo", default=True, db_index=True)
    origin = models.CharField("origem", max_length=30, choices=Origin, default=Origin.STARHUB)
    created_at = models.DateTimeField("criado em", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("alterado em", auto_now=True, db_index=True)
    metadados = models.JSONField("metadados", default=list, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="criado por", null=True, blank=True, editable=False,
        on_delete=models.SET_NULL, related_name="%(app_label)s_%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="alterado por", null=True, blank=True,
        editable=False,
        on_delete=models.SET_NULL, related_name="%(app_label)s_%(class)s_updated",
    )
    historical = HistoricalRecords(inherit=True, get_user=usuario_do_historico)

    objects = TenantManager()
    all_objects = UnscopedManager()

    class Meta:
        abstract = True
        base_manager_name = "all_objects"
        default_manager_name = "objects"

    def save(self, *args, **kwargs):
        current_account_id = get_current_account_id(required=False)
        if not self.account_id:
            # Filho herda a conta do pai; sem pai, vale a conta ativa.
            self.account_id = conta_herdada(self) or current_account_id
        if not self.account_id:
            raise TenantMismatchError("Registro tenant-aware exige account_id.")
        outra_conta = current_account_id and str(self.account_id) != str(current_account_id)
        if outra_conta and not ve_todas_as_contas():
            raise TenantMismatchError("Nao e permitido gravar dados em outra conta.")
        validate_model_relations(self)
        user = get_current_user()
        if user and getattr(user, "pk", None):
            if self._state.adding and not self.created_by_id:
                self.created_by = user
            self.updated_by = user
        return super().save(*args, **kwargs)
