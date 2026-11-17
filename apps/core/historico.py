"""Versoes do simple_history de um registro (e dos que pertencem a ele) e o reverter.

Toda gravacao gera uma versao, venha do admin, da API Woo, de webhook ou de tarefa
(apps/core/origem.py poe o autor e o motivo: "woo_api - ERP (...a1b2) - tarefa #12").
O botao "Historico" da edicao lista essas versoes com o que mudou em cada uma; reverter
copia os campos da versao escolhida para o registro e salva pelo save() normal, entao
regra do model, log e envio as lojas acontecem como numa edicao.
"""

import re
from heapq import merge

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from apps.core import log_valores

POR_PAGINA = 50
# Identidade e dono do registro: voltar estes campos trocaria o registro de conta ou de id.
PROTEGIDOS = {"uuid", "account", "created_at", "created_by"}
TIPOS = {"+": ("criacao", "success"), "~": ("alteracao", "info"), "-": ("exclusao", "destructive")}
TAREFA = re.compile(r"tarefa #(\d+)")


def manager(modelo):
    nome = getattr(modelo._meta, "simple_history_manager_attribute", None) if modelo else None
    return getattr(modelo, nome) if nome else None


def _versoes_do_tipo(tipo, pks, quantas):
    modelo = ContentType.objects.get_for_id(tipo).model_class()
    historico = manager(modelo)
    if historico is None:
        return []
    campo_pk = modelo._meta.pk.attname
    consulta = (historico.filter(**{f"{campo_pk}__in": sorted(pks)})
                .select_related("history_user").order_by("-history_date", "-history_id"))
    return [(versao, tipo, modelo) for versao in consulta[:quantas]]


def versoes(alvo, pagina=1):
    """Pagina de versoes de todos os registros do alvo, mais recentes primeiro."""
    quantas = POR_PAGINA * pagina + 1
    listas = [_versoes_do_tipo(tipo, pks, quantas) for tipo, pks in alvo.items()]
    juntas = list(merge(*listas, key=lambda item: item[0].history_date, reverse=True))
    inicio = POR_PAGINA * (pagina - 1)
    return [_linha(*item) for item in juntas[inicio:inicio + POR_PAGINA]], len(juntas) >= quantas


def _mudancas(modelo, versao):
    if versao.history_type != "~":
        return []
    anterior = versao.prev_record
    if anterior is None:
        return []
    delta = versao.diff_against(anterior)
    return [(log_valores.rotulo(modelo, m.field), log_valores.legivel(modelo, m.field, m.old),
             log_valores.legivel(modelo, m.field, m.new)) for m in delta.changes]


def _linha(versao, tipo, modelo):
    acao, tom = TIPOS.get(versao.history_type, ("-", "secondary"))
    usuario = versao.history_user
    motivo = versao.history_change_reason or ""
    tarefa = TAREFA.search(motivo)
    return {
        "versao": versao, "tipo": tipo, "acao": acao, "tom": tom,
        "tipo_registro": str(modelo._meta.verbose_name).capitalize(),
        "registro": str(versao.instance),
        "pk": getattr(versao, modelo._meta.pk.attname),
        "autor": (usuario.get_full_name() or usuario.get_username()) if usuario else "",
        "motivo": motivo,
        "tarefa_id": tarefa.group(1) if tarefa else "",
        "mudancas": _mudancas(modelo, versao),
    }


def comparar(modelo, atual, versao):
    """[(rotulo, valor de agora, valor da versao)] do que o reverter vai trocar."""
    linhas = []
    for campo in _campos(modelo, restaurando=atual is None):
        agora = getattr(atual, campo.attname) if atual is not None else None
        antes = getattr(versao, campo.attname)
        if agora != antes:
            linhas.append((log_valores.rotulo(modelo, campo.name),
                           log_valores.legivel(modelo, campo.name, agora),
                           log_valores.legivel(modelo, campo.name, antes)))
    return linhas


def _campos(modelo, restaurando):
    for campo in modelo._meta.concrete_fields:
        if campo.primary_key or getattr(campo, "auto_now", False):
            continue
        if campo.name in PROTEGIDOS and not restaurando:
            continue
        yield campo


def reverter(modelo, versao, consulta):
    """Volta o registro para a versao; `consulta` e o manager com o filtro de conta.

    Registro excluido volta a existir com o mesmo id (restaurar). O lock evita que uma
    edicao no meio do caminho seja sobrescrita por um retrato misturado.
    """
    pk = getattr(versao, modelo._meta.pk.attname)
    with transaction.atomic():
        atual = consulta.select_for_update().filter(pk=pk).first()
        restaurando = atual is None
        alvo = modelo(pk=pk) if restaurando else atual
        for campo in _campos(modelo, restaurando):
            setattr(alvo, campo.attname, getattr(versao, campo.attname))
        alvo._change_reason = f"revertido para a versao #{versao.history_id}"[:100]
        alvo.save()
    return alvo
