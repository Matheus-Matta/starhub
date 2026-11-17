"""De onde veio a alteracao (admin, woo_api, shopify...), gravada em cada log e versao.

O auditlog so conhece o usuario do login do Django: alteracao feita pela API (chave
ck_ ou JWT, autenticados pelo DRF depois dos middlewares) ficava como "system".
Aqui a requisicao (ou a integracao) diz a origem, e o log guarda em additional_data:

    {"origem": "woo_api", "via": "ERP (...a1b2)", "tarefa_id": 12,
     "requisicao": {"metodo": "PUT", "caminho": "/wp-json/wc/v3/products/5", "ip": "..."}}

- admin: OrigemMiddleware, em /admin/ (o usuario ja vai no log pelo auditlog).
- woo_api: WooView.initial, depois de autenticar (via = chave ou usuario do JWT).
- integracoes (shopify, mercado_livre...): envolva o trabalho em
  `with origem("shopify", via="Loja X", tarefa=execucao.pk):`.
- fora disso (comando, shell, tarefa): "sistema".

A tarefa liga o log a tela de Tarefas (requisicao e resposta completas ficam la) e
vira o id de correlacao: "tarefa-12" junta tudo o que a tarefa alterou. Sem tarefa,
cada requisicao ganha um id proprio pelo mesmo motivo.
O historico (simple_history) recebe o mesmo: autor e um resumo em history_change_reason,
porque sem request o simple_history gravava a versao sem autor nem motivo.
"""

import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse

from apps.core.tenant.context import get_current_user

ADMIN = "admin"
WOO_API = "woo_api"
SISTEMA = "sistema"
LIMITE_MOTIVO = 100  # history_change_reason e CharField(100)

_atual = ContextVar("starhub_origem", default=None)


def definir(codigo, via="", ator=None, tarefa=None, requisicao=None):
    """Liga a origem; devolve o token para `restaurar`. `ator`: User que fez (JWT)."""
    anterior = _atual.get() or {}
    # A origem de dentro (envio aberto por um save do admin) herda a requisicao de fora.
    requisicao = requisicao or anterior.get("requisicao")
    correlacao = f"tarefa-{tarefa}" if tarefa else anterior.get("correlacao") or uuid.uuid4().hex
    return _atual.set({"origem": codigo, "via": str(via or ""), "ator": ator,
                       "tarefa": tarefa, "requisicao": requisicao, "correlacao": correlacao})


def restaurar(token):
    _atual.reset(token)


@contextmanager
def origem(codigo, via="", ator=None, tarefa=None, requisicao=None):
    token = definir(codigo, via, ator, tarefa, requisicao)
    try:
        yield
    finally:
        restaurar(token)


def requisicao_de(request):
    """Metodo, caminho e IP: o bastante para achar a chamada; o corpo fica na tarefa."""
    encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = encaminhado.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")
    return {"metodo": request.method, "caminho": request.path[:300], "ip": ip}


def _ator(atual):
    ator = atual.get("ator") or get_current_user()
    return ator if isinstance(ator, get_user_model()) and ator.pk else None


def marcar_log(sender, instance, **kwargs):
    """pre_save do LogEntry: grava origem, tarefa, requisicao e o autor, se a API sabe."""
    if instance.pk:
        return
    atual = _atual.get() or {"origem": SISTEMA}
    dados = dict(instance.additional_data or {})
    dados.setdefault("origem", atual["origem"])
    for chave, valor in (("via", atual.get("via")), ("tarefa_id", atual.get("tarefa")),
                         ("requisicao", atual.get("requisicao"))):
        if valor:
            dados.setdefault(chave, valor)
    instance.additional_data = dados
    if not instance.cid and atual.get("correlacao"):
        instance.cid = atual["correlacao"]
    ator = _ator(atual)
    if instance.actor_id is None and ator is not None:
        instance.actor = ator
        instance.actor_email = getattr(ator, "email", None)


def resumo():
    """"woo_api - ERP (...a1b2) - tarefa #12": o motivo da versao no historico."""
    atual = _atual.get() or {"origem": SISTEMA}
    partes = [atual["origem"], atual.get("via"),
              f"tarefa #{atual['tarefa']}" if atual.get("tarefa") else ""]
    return " - ".join(parte for parte in partes if parte)[:LIMITE_MOTIVO]


def marcar_historico(sender, history_instance, **kwargs):
    """pre_create_historical_record: autor e motivo quando nao veio de um form do admin."""
    if history_instance.history_user_id is None:
        ator = _ator(_atual.get() or {})
        if ator is not None:
            history_instance.history_user = ator
    if not history_instance.history_change_reason:
        history_instance.history_change_reason = resumo()


def _eh_admin(request):
    try:
        return request.path.startswith(reverse("admin:index"))
    except NoReverseMatch:
        return False


def OrigemMiddleware(get_response):
    def middleware(request):
        if not _eh_admin(request):
            return get_response(request)
        with origem(ADMIN, requisicao=requisicao_de(request)):
            return get_response(request)

    return middleware


def atual():
    """Codigo da origem ligada agora ("sistema" fora de admin, API e integracao)."""
    return (_atual.get() or {}).get("origem") or SISTEMA


def tarefa_atual():
    """Id da tarefa que esta rodando agora, ou None."""
    return (_atual.get() or {}).get("tarefa")
