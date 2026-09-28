"""Erros no formato do WordPress/WooCommerce: {"code", "message", "data": {"status"}}.

O ERP le o `code` para decidir o que fazer; por isso os codigos sao os mesmos
do Woo, e nao os do DRF.
"""

from rest_framework import exceptions, status
from rest_framework.response import Response


class WooErro(Exception):
    def __init__(self, codigo, mensagem, status_http=400, dados=None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.status_http = status_http
        self.dados = dados or {}

    def como_dict(self):
        return {
            "code": self.codigo,
            "message": self.mensagem,
            "data": {"status": self.status_http, **self.dados},
        }


def parametro_invalido(campo, detalhe):
    return WooErro(
        "rest_invalid_param",
        f"Parametro(s) invalido(s): {campo}",
        400,
        {"params": {campo: detalhe}},
    )


def id_invalido(recurso):
    return WooErro(f"woocommerce_rest_{recurso}_invalid_id", "ID invalido.", 404)


def _traduzir(exc):
    if isinstance(exc, WooErro):
        return exc
    if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        detalhe = str(exc.detail) if exc.detail else "Autenticacao necessaria."
        return WooErro("woocommerce_rest_authentication_error", detalhe, 401)
    if isinstance(exc, exceptions.PermissionDenied):
        return WooErro("woocommerce_rest_cannot_view", str(exc.detail), 403)
    if isinstance(exc, exceptions.MethodNotAllowed):
        return WooErro("rest_no_route", "Nenhuma rota para este metodo.", 404)
    if isinstance(exc, exceptions.ParseError):
        return WooErro("rest_invalid_json", "Corpo JSON invalido.", 400)
    if isinstance(exc, exceptions.Throttled):
        return WooErro("rest_too_many_requests", "Muitas tentativas; aguarde.", 429)
    if isinstance(exc, exceptions.APIException):
        return WooErro("rest_error", str(exc.detail), exc.status_code)
    return None


def tratar_excecao(exc, context):
    erro = _traduzir(exc)
    if erro is None:
        return None  # erro de programacao: deixa subir e aparecer no log como 500
    resposta = Response(erro.como_dict(), status=erro.status_http)
    if erro.status_http == status.HTTP_401_UNAUTHORIZED:
        resposta["WWW-Authenticate"] = 'Basic realm="WooCommerce API"'
    return resposta
