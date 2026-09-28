from contextlib import contextmanager
from contextvars import ContextVar

from django.db.models import Model

from .exceptions import TenantContextMissing

_account_id = ContextVar("starhub_account_id", default=None)
_user = ContextVar("starhub_user", default=None)
# Superusuario no admin: consultas sem filtro de conta. Nunca liga sozinho; so o
# TenantMiddleware liga, e so em /admin/ (a API continua isolada para todos).
_todas_as_contas = ContextVar("starhub_todas_as_contas", default=False)


def get_current_account_id(required=True):
    account_id = _account_id.get()
    if required and account_id is None:
        raise TenantContextMissing("Nenhuma conta ativa foi definida para esta operacao.")
    return account_id


def get_current_user():
    return _user.get()


def ve_todas_as_contas():
    return _todas_as_contas.get()


def usuario_do_historico(request=None, **kwargs):
    """history_user do simple_history: so um User de verdade.

    Na API por chave ck_ o request.user e a propria chave (sem User); gravar isso
    no historico quebra a FK. Nesse caso o historico fica sem autor.
    """
    user = getattr(request, "user", None)
    return user if isinstance(user, Model) and user.is_authenticated else None


def bind_tenant(account_id, user=None, todas_as_contas=False):
    """account_id continua sendo a conta do usuario (padrao ao criar), mesmo quando
    todas_as_contas=True libera a leitura das outras."""
    return (
        _account_id.set(account_id), _user.set(user), _todas_as_contas.set(todas_as_contas)
    )


def reset_tenant(tokens):
    account_token, user_token, todas_token = tokens
    _todas_as_contas.reset(todas_token)
    _user.reset(user_token)
    _account_id.reset(account_token)


@contextmanager
def tenant_context(account_or_id, user=None):
    account_id = getattr(account_or_id, "pk", account_or_id)
    tokens = bind_tenant(account_id, user)
    try:
        yield account_id
    finally:
        reset_tenant(tokens)
