from rest_framework import exceptions, permissions

from apps.woo_api.models import ChaveApi


class PodeUsarApiWoo(permissions.BasePermission):
    """Chave ck_/cs_: vale a permissao da chave (leitura, escrita ou as duas).
    JWT: o usuario precisa da permissao `woo_api.usar_api` (superusuario ja tem)."""

    def has_permission(self, request, view):
        usuario = request.user
        if not usuario or not usuario.is_authenticated:
            return False
        if isinstance(request.auth, ChaveApi):
            if not request.auth.permite(request.method):
                # Mesmo codigo e status (401) que o Woo devolve nesse caso.
                raise exceptions.AuthenticationFailed(
                    f"A chave de API nao tem permissao de "
                    f"{'leitura' if request.method == 'GET' else 'escrita'}."
                )
            return True
        return usuario.has_perm("woo_api.usar_api")
