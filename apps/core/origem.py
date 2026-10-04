"""De onde veio a alteracao (admin, woo_api, shopify...), gravada em cada log do auditlog.

O auditlog so conhece o usuario do login do Django: alteracao feita pela API (chave
ck_ ou JWT, autenticados pelo DRF depois dos middlewares) ficava como "system".
Aqui a requisicao (ou a integracao) diz a origem, e o log guarda em additional_data:

    {"origem": "woo_api", "via": "ERP (...a1b2)"}

- admin: OrigemMiddleware, em /admin/ (o usuario ja vai no log pelo auditlog).
- woo_api: WooView.initial, depois de autenticar (via = chave ou usuario do JWT).
- integracoes (shopify, mercado_livre...): envolva o trabalho em
  `with origem("shopify", via="Loja X"):`.
- fora disso (comando, shell, tarefa): "sistema".
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse

ADMIN = "admin"
WOO_API = "woo_api"
SISTEMA = "sistema"

_atual = ContextVar("starhub_origem", default=None)


def definir(codigo, via="", ator=None):
    """Liga a origem; devolve o token para `restaurar`. `ator`: User que fez (JWT)."""
    return _atual.set({"origem": codigo, "via": str(via or ""), "ator": ator})


def restaurar(token):
    _atual.reset(token)


@contextmanager
def origem(codigo, via="", ator=None):
    token = definir(codigo, via, ator)
    try:
        yield
    finally:
        restaurar(token)


def marcar_log(sender, instance, **kwargs):
    """pre_save do LogEntry: grava a origem (e o autor, se a API sabe quem e)."""
    if instance.pk:
        return
    atual = _atual.get() or {"origem": SISTEMA}
    dados = dict(instance.additional_data or {})
    dados.setdefault("origem", atual["origem"])
    if atual.get("via"):
        dados.setdefault("via", atual["via"])
    instance.additional_data = dados
    ator = atual.get("ator")
    if instance.actor_id is None and isinstance(ator, get_user_model()):
        instance.actor = ator
        instance.actor_email = getattr(ator, "email", None)


def _eh_admin(request):
    try:
        return request.path.startswith(reverse("admin:index"))
    except NoReverseMatch:
        return False


def OrigemMiddleware(get_response):
    def middleware(request):
        if not _eh_admin(request):
            return get_response(request)
        with origem(ADMIN):
            return get_response(request)

    return middleware


def atual():
    """Codigo da origem ligada agora ("sistema" fora de admin, API e integracao)."""
    return (_atual.get() or {}).get("origem") or SISTEMA
