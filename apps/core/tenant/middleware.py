from inspect import iscoroutinefunction

from asgiref.sync import markcoroutinefunction
from django.core.exceptions import PermissionDenied
from django.db.models import Model, QuerySet
from django.urls import NoReverseMatch, reverse

from .context import bind_tenant, reset_tenant
from .exceptions import TenantMismatchError


def _assert_value(value, account_id, depth=0):
    if depth > 4 or value is None:
        return
    if isinstance(value, Model) and hasattr(value, "account_id"):
        if value.account_id != account_id:
            raise TenantMismatchError("A resposta contem dado pertencente a outra conta.")
    elif isinstance(value, QuerySet) and hasattr(value.model, "account"):
        if value.query.is_sliced:
            # Fatia ([:6] do painel) nao aceita exclude(): confere linha a linha.
            for item in value:
                _assert_value(item, account_id, depth + 1)
        elif value.exclude(account_id=account_id).exists():
            raise TenantMismatchError("A resposta contem dados pertencentes a outra conta.")
    elif isinstance(value, dict):
        for item in value.values():
            _assert_value(item, account_id, depth + 1)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            _assert_value(item, account_id, depth + 1)


def validate_tenant_response(response, account_id):
    _assert_value(getattr(response, "tenant_objects", None), account_id)
    _assert_value(getattr(response, "context_data", None), account_id)


def _no_admin(request):
    try:
        return request.path.startswith(reverse("admin:index"))
    except NoReverseMatch:
        return False


def _bind_request(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None
    if not user.account_id:
        raise PermissionDenied("O usuario autenticado nao possui uma conta.")
    # Decisao do produto: no admin o superusuario ve todas as contas (com coluna e
    # filtro "Conta" nas listagens). Fora do admin, inclusive na API, ninguem ve.
    todas = bool(user.is_superuser) and _no_admin(request)
    request.tenant_todas_as_contas = todas
    return bind_tenant(user.account_id, user, todas_as_contas=todas)


def _validar_saida(request, response):
    if not getattr(request, "tenant_todas_as_contas", False):
        validate_tenant_response(response, request.user.account_id)


def TenantMiddleware(get_response):
    if iscoroutinefunction(get_response):
        async def middleware(request):
            tokens = _bind_request(request)
            try:
                response = await get_response(request)
                if tokens:
                    _validar_saida(request, response)
                return response
            finally:
                if tokens:
                    reset_tenant(tokens)

        markcoroutinefunction(middleware)
        return middleware

    def middleware(request):
        tokens = _bind_request(request)
        try:
            response = get_response(request)
            if tokens:
                _validar_saida(request, response)
            return response
        finally:
            if tokens:
                reset_tenant(tokens)

    return middleware
