from django.db import models
from django.db.models import Q

from .context import get_current_account_id, ve_todas_as_contas
from .exceptions import TenantMismatchError
from .validators import conta_do_registro, validate_model_relations

TENANT_FIELDS = {"account", "account_id"}


def _prepare_account(values, account_id):
    if ve_todas_as_contas():
        # Superusuario no admin: a conta vem do formulario ou do registro pai (save()).
        return values
    informed = values.get("account_id") or getattr(values.get("account"), "pk", None)
    if informed is not None and str(informed) != str(account_id):
        raise TenantMismatchError("Nao e permitido gravar dados em outra conta.")
    values.setdefault("account_id", account_id)
    return values


class TenantQuerySet(models.QuerySet):
    _tenant_bound_id = None

    def _clone(self):
        clone = super()._clone()
        clone._tenant_bound_id = self._tenant_bound_id
        return clone

    def _bind_tenant(self):
        account_id = get_current_account_id()
        if ve_todas_as_contas():
            return account_id
        if self._tenant_bound_id is None:
            self.query.add_q(Q(account_id=account_id))
            self._tenant_bound_id = account_id
        elif str(self._tenant_bound_id) != str(account_id):
            raise TenantMismatchError("O queryset foi criado no contexto de outra conta.")
        return account_id

    def _fetch_all(self):
        self._bind_tenant()
        return super()._fetch_all()

    def iterator(self, *args, **kwargs):
        self._bind_tenant()
        return super().iterator(*args, **kwargs)

    def count(self):
        self._bind_tenant()
        return super().count()

    def exists(self):
        self._bind_tenant()
        return super().exists()

    def aggregate(self, *args, **kwargs):
        self._bind_tenant()
        return super().aggregate(*args, **kwargs)

    def create(self, **kwargs):
        return super().create(**_prepare_account(kwargs, get_current_account_id()))

    def get_or_create(self, defaults=None, **kwargs):
        account_id = get_current_account_id()
        return super().get_or_create(
            defaults=_prepare_account(defaults or {}, account_id),
            **_prepare_account(kwargs, account_id),
        )

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        account_id = get_current_account_id()
        defaults = _prepare_account(defaults or {}, account_id)
        if create_defaults is not None:
            create_defaults = _prepare_account(create_defaults, account_id)
        lookup = _prepare_account(kwargs, account_id)
        return super().update_or_create(
            defaults=defaults, create_defaults=create_defaults, **lookup
        )

    def update(self, **kwargs):
        self._bind_tenant()
        if TENANT_FIELDS.intersection(kwargs):
            raise TenantMismatchError("O account_id de um registro nao pode ser alterado.")
        return super().update(**kwargs)

    def delete(self):
        self._bind_tenant()
        return super().delete()

    def bulk_create(self, objs, **kwargs):
        account_id = get_current_account_id()
        todas = ve_todas_as_contas()
        for obj in objs:
            if todas:
                obj.account_id = conta_do_registro(obj)
            elif obj.account_id is not None and str(obj.account_id) != str(account_id):
                raise TenantMismatchError("O lote contem registro de outra conta.")
            else:
                obj.account_id = account_id
            validate_model_relations(obj)
        return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        if TENANT_FIELDS.intersection(fields):
            raise TenantMismatchError("bulk_update nao pode alterar account_id.")
        account_id = get_current_account_id()
        for obj in objs:
            if not ve_todas_as_contas() and str(obj.account_id) != str(account_id):
                raise TenantMismatchError("O lote contem registro de outra conta.")
            validate_model_relations(obj)
        return super().bulk_update(objs, fields, **kwargs)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    use_in_migrations = False

    def get_queryset(self):
        return super().get_queryset()


class UnscopedManager(models.Manager):
    """Acesso interno explicito; nunca usar em views ou serializers comuns."""

    use_in_migrations = False
