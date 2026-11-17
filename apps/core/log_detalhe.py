"""O que a tela de um log mostra: quem, por onde, qual requisicao/tarefa e o que mudou.

A tela padrao do auditlog dizia "Alterado por: None -> 2" e nada mais. Aqui:
- quem: o usuario (nome e e-mail), a origem (admin, woo_api, shopify...) e a chave/loja;
- de onde: metodo, caminho e IP da requisicao; a tarefa, com o corpo e a resposta inteiros;
- o que mudou: rotulo do campo e valores legiveis (apps/core/log_valores.py);
- o registro inteiro como ficou depois da alteracao (serialized_data).
"""

from auditlog.models import LogEntry
from django.apps import apps
from django.urls import NoReverseMatch, reverse
from django.utils.http import urlencode

from apps.core import log_valores, origem

ACOES = {
    LogEntry.Action.CREATE: "criacao", LogEntry.Action.UPDATE: "alteracao",
    LogEntry.Action.DELETE: "exclusao", LogEntry.Action.ACCESS: "acesso",
}
TONS_ACAO = {LogEntry.Action.CREATE: "success", LogEntry.Action.UPDATE: "info",
             LogEntry.Action.DELETE: "destructive"}
TONS_ORIGEM = {origem.ADMIN: "secondary", origem.SISTEMA: "secondary"}


def _url(rota, *args):
    try:
        return reverse(rota, args=args)
    except NoReverseMatch:
        return ""


def url_registro(log):
    """Edicao do registro, se ele ainda existe e tem tela no admin."""
    modelo = log.content_type.model_class() if log.content_type_id else None
    if modelo is None or not modelo._base_manager.filter(pk=log.object_pk).exists():
        return ""
    return _url(f"admin:{modelo._meta.app_label}_{modelo._meta.model_name}_change", log.object_pk)


def tarefa(log):
    """{"id", "nome", "url"} da tarefa em que a alteracao aconteceu, ou None."""
    tarefa_id = (log.additional_data or {}).get("tarefa_id")
    if not tarefa_id:
        return None
    Execucao = apps.get_model("integracoes", "ExecucaoIntegracao")
    execucao = Execucao.all_objects.filter(pk=tarefa_id).first()
    return {
        "id": tarefa_id,
        "nome": execucao.get_tipo_display() if execucao else "tarefa excluida",
        "url": _url("admin:integracoes_execucaointegracao_change", tarefa_id) if execucao else "",
    }


def autor(log):
    """(nome, url) de quem fez; usuario sem tela no admin fica sem link."""
    if not log.actor_id:
        return "", ""
    usuario = log.actor
    nome = usuario.get_full_name() or usuario.get_username()
    if usuario.email and usuario.email not in nome:
        nome = f"{nome} <{usuario.email}>"
    rota = f"admin:{usuario._meta.app_label}_{usuario._meta.model_name}_change"
    return nome, _url(rota, usuario.pk)


def contexto(log):
    dados = log.additional_data or {}
    modelo = log.content_type.model_class() if log.content_type_id else None
    codigo = dados.get("origem") or origem.SISTEMA
    nome_autor, url_autor = autor(log)
    requisicao = dados.get("requisicao") or {}
    lista = _url("admin:auditlog_logentry_changelist")
    return {
        "acao": ACOES.get(log.action, log.action),
        "tom_acao": TONS_ACAO.get(log.action, "secondary"),
        "origem": codigo,
        "tom_origem": TONS_ORIGEM.get(codigo, "primary"),
        "via": dados.get("via", ""),
        "nome_autor": nome_autor,
        "url_autor": url_autor,
        "requisicao_linha": " ".join(
            filter(None, [requisicao.get("metodo"), requisicao.get("caminho")])),
        "ip": requisicao.get("ip") or log.remote_addr or "",
        "tarefa": tarefa(log),
        "url_correlacao": f"{lista}?{urlencode({'cid': log.cid})}" if log.cid else "",
        "url_registro": url_registro(log),
        "tipo_registro": str(log.content_type.name).capitalize() if log.content_type_id else "",
        "mudancas": log_valores.mudancas(modelo, log.changes_dict),
        "retrato": log_valores.retrato(modelo, log.serialized_data),
    }


def campos_alterados(log):
    """"Nome, Preco, Estoque": a coluna da lista diz o que mudou sem abrir o log."""
    modelo = log.content_type.model_class() if log.content_type_id else None
    nomes = [log_valores.rotulo(modelo, nome) for nome in (log.changes_dict or {})]
    texto = ", ".join(nomes[:6])
    return f"{texto} e mais {len(nomes) - 6}" if len(nomes) > 6 else texto or "-"
