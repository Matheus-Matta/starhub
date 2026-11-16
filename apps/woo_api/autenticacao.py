"""Os dois jeitos de o ERP entrar, os mesmos de uma loja WooCommerce real:

1. JWT (plugin "JWT Authentication for WP REST API"):
   POST /wp-json/jwt-auth/v1/token -> token; depois "Authorization: Bearer <token>".
2. Chave de API do Woo (consumer key/secret):
   Basic Auth com ck_ como usuario e cs_ como senha, ou ?consumer_key=&consumer_secret=.
"""

import base64
import binascii

from django.utils import timezone
from rest_framework import authentication, exceptions

from apps.woo_api import chaves
from apps.woo_api.models import ChaveApi


def _credenciais(request):
    cabecalho = authentication.get_authorization_header(request).split()
    if cabecalho and cabecalho[0].lower() == b"basic" and len(cabecalho) == 2:
        try:
            usuario, _, senha = base64.b64decode(cabecalho[1]).decode().partition(":")
        except (binascii.Error, UnicodeDecodeError) as erro:
            raise exceptions.AuthenticationFailed("Cabecalho Basic invalido.") from erro
        return usuario, senha
    params = request.query_params
    if "consumer_key" in params:
        return params.get("consumer_key"), params.get("consumer_secret", "")
    return None, None


class UsuarioDaChave:
    """request.user de quem entrou com chave ck_/cs_. A chave pertence a conta,
    nao a uma pessoa: por isso nao ha User, so a conta e a propria chave."""

    is_authenticated = True
    is_anonymous = False
    is_active = True
    is_superuser = False
    pk = id = None

    def __init__(self, chave):
        self.chave = chave
        self.account_id = chave.account_id

    def __str__(self):
        return str(self.chave)

    def has_perm(self, perm, obj=None):
        return False


class ChaveConsumidorAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        chave, segredo = _credenciais(request)
        if not chave or not chave.startswith("ck_"):
            return None  # nao e chave do Woo: deixa o proximo metodo tentar
        # all_objects de proposito: a conta ainda nao e conhecida, e a chave que a define.
        registro = (
            ChaveApi.all_objects.select_related("account")
            .filter(chave_hash=chaves.hash_de(chave))
            .first()
        )
        if registro is None:
            raise exceptions.AuthenticationFailed("Chave de consumidor invalida.")
        if not chaves.segredo_confere(registro.segredo_hash, segredo):
            raise exceptions.AuthenticationFailed("Segredo de consumidor invalido.")
        if not registro.active or registro.expirada or not registro.account.active:
            raise exceptions.AuthenticationFailed("Chave de API inativa ou expirada.")
        # update() direto: nao dispara save/signal e nao disputa lock com outra requisicao.
        ChaveApi.all_objects.filter(pk=registro.pk).update(last_used_at=timezone.now())
        return UsuarioDaChave(registro), registro

    def authenticate_header(self, request):
        return 'Basic realm="WooCommerce API"'
