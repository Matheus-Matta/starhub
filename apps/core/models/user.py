from django.contrib.auth.models import AbstractUser, UserManager
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.tenant.context import get_current_account_id
from apps.core.tenant.exceptions import TenantContextMissing


class AccountUserManager(UserManager):
    def _account(self, extra_fields):
        account = extra_fields.get("account")
        if account is not None and not hasattr(account, "pk"):
            # createsuperuser entrega a chave digitada no prompt, nao a instancia.
            extra_fields["account_id"] = extra_fields.pop("account")
        if extra_fields.get("account") or extra_fields.get("account_id"):
            return extra_fields
        account_id = get_current_account_id(required=False)
        if account_id is None:
            raise TenantContextMissing("Informe a conta para criar o usuario.")
        extra_fields["account_id"] = account_id
        return extra_fields

    def _create_user(self, username, email, password, **extra_fields):
        return super()._create_user(username, email, password, **self._account(extra_fields))


class User(AbstractUser):
    account = models.ForeignKey(
        "core.Account", verbose_name="conta", on_delete=models.PROTECT, related_name="users"
    )
    access_profile = models.ForeignKey(
        "core.AccessProfile", verbose_name="perfil de acesso", null=True, blank=True,
        on_delete=models.PROTECT, related_name="users",
    )

    objects = AccountUserManager()

    # createsuperuser pergunta a conta: nenhum usuario nasce fora de um tenant.
    REQUIRED_FIELDS = ["email", "account"]

    class Meta(AbstractUser.Meta):
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def clean(self):
        super().clean()
        if self.access_profile_id and self.access_profile.account_id != self.account_id:
            raise ValidationError({"access_profile": "O perfil pertence a outra conta."})
