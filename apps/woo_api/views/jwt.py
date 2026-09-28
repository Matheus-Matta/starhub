"""Rotas do plugin "JWT Authentication for WP REST API", com as mesmas respostas.

Exemplo:
    POST /wp-json/jwt-auth/v1/token  {"username": "erp", "password": "..."}
    -> {"token": "...", "user_email": "...", "user_nicename": "erp", "user_display_name": "ERP"}
"""

from django.contrib.auth import authenticate, get_user_model
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken

from apps.woo_api.erros import WooErro
from apps.woo_api.parsers import JSONDecimalParser, JSONQualquerTipo
from apps.woo_api.views.base import tratar_erro_woo


def _autenticar(request, login, senha):
    usuario = authenticate(request, username=login, password=senha)
    if usuario is None and "@" in login:
        # O WordPress aceita e-mail no lugar do usuario.
        encontrado = get_user_model().objects.filter(email__iexact=login).first()
        if encontrado:
            usuario = authenticate(request, username=encontrado.get_username(), password=senha)
    return usuario


class TokenView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [JSONDecimalParser, FormParser, MultiPartParser, JSONQualquerTipo]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "jwt_login"

    def get_exception_handler(self):
        return tratar_erro_woo

    def post(self, request):
        dados = request.data if isinstance(request.data, dict) else {}
        login = str(dados.get("username") or "").strip()
        senha = str(dados.get("password") or "")
        usuario = _autenticar(request, login, senha) if login and senha else None
        if usuario is None or not usuario.is_active:
            # Mensagem unica para usuario e senha: nao revela quais usuarios existem.
            raise WooErro("[jwt_auth] incorrect_password", "Usuario ou senha incorretos.", 403)
        return Response({
            "token": str(AccessToken.for_user(usuario)),
            "user_email": usuario.email,
            "user_nicename": usuario.get_username(),
            "user_display_name": usuario.get_full_name() or usuario.get_username(),
        })


class ValidarTokenView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return tratar_erro_woo

    def post(self, request):
        return Response({"code": "jwt_auth_valid_token", "data": {"status": 200}})
