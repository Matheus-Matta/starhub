from django.core.exceptions import ValidationError

from .context import get_current_account_id
from .exceptions import TenantMismatchError


def _relacoes_com_conta(instance):
    """(campo, id) das FKs para models tenant-aware (os que tem all_objects)."""
    for field in instance._meta.concrete_fields:
        if not field.is_relation or not field.many_to_one:
            continue
        related_id = getattr(instance, field.attname, None)
        if related_id is not None and hasattr(field.remote_field.model, "all_objects"):
            yield field, related_id


def conta_herdada(instance):
    """Conta do primeiro "pai" do registro: item do pedido herda a do pedido.

    Importa quando o superusuario, no admin, cria filho de um registro de OUTRA
    conta: a conta ativa (a dele) seria a errada.
    """
    for field, related_id in _relacoes_com_conta(instance):
        pai = field.get_cached_value(instance, None)
        if pai is not None:
            return pai.account_id
        return (
            field.remote_field.model.all_objects.filter(pk=related_id)
            .values_list("account_id", flat=True).first()
        )
    return None


def conta_do_registro(instance):
    """A conta que o registro tem ou vai ter ao salvar."""
    return (
        getattr(instance, "account_id", None)
        or conta_herdada(instance)
        or get_current_account_id(required=False)
    )


def validate_same_account(instance, *related_objects):
    # Objeto novo so recebe a conta no save(); no clean() do form ela e deduzida.
    account_id = conta_do_registro(instance)
    for related in related_objects:
        if related is None or not hasattr(related, "account_id"):
            continue
        if related.account_id != account_id:
            raise ValidationError("O relacionamento pertence a outra conta.")


def validate_model_relations(instance):
    for field, related_id in _relacoes_com_conta(instance):
        related = field.remote_field.model.all_objects.only("account_id").get(pk=related_id)
        if related.account_id != instance.account_id:
            raise TenantMismatchError(
                f"{field.name} pertence a outra conta e nao pode ser associado."
            )
