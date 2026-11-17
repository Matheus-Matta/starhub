"""Valor do log como o operador le: rotulo do campo, nome no lugar do id, Sim/Nao.

O auditlog guarda o que esta no banco: "Alterado por: None -> 2" nao diz nada.
Aqui o campo vira o verbose_name do model ("Alterado por"), a FK vira o registro
("maria (#2)"), a escolha vira o rotulo ("Publicado") e o booleano vira Sim/Nao.
"""

import json

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.utils import dateparse, timezone

VAZIO = "-"
LIMITE = 2000  # texto longo (descricao HTML) corta: a tela e para ler, nao para copiar


def campo(modelo, nome):
    if modelo is None:
        return None
    try:
        return modelo._meta.get_field(nome)
    except FieldDoesNotExist:
        # O retrato do auditlog usa o nome; o historico guarda o attname ("categoria_id").
        return next((c for c in modelo._meta.concrete_fields if c.attname == nome), None)


def rotulo(modelo, nome):
    encontrado = campo(modelo, nome)
    texto = getattr(encontrado, "verbose_name", None) or nome
    return str(texto)[:1].upper() + str(texto)[1:]


def _vazio(valor):
    return valor is None or valor in ("", "None", "null", [], {})


def _relacionado(encontrado, valor):
    destino = encontrado.related_model
    obj = destino._base_manager.filter(pk=valor).first()
    return f"{obj} (#{valor})" if obj is not None else f"#{valor} (excluido)"


def _texto(valor):
    if isinstance(valor, (dict, list)):
        valor = json.dumps(valor, ensure_ascii=False, default=str)
    texto = str(valor)
    return texto if len(texto) <= LIMITE else f"{texto[:LIMITE]}... (cortado)"


def _data(encontrado, valor):
    """"2026-11-17T16:10:52Z" vira "17/11/2026 13:10:52" (hora local, como a tela mostra)."""
    texto = valor.isoformat() if hasattr(valor, "isoformat") else str(valor)
    if isinstance(encontrado, models.DateTimeField):
        data = dateparse.parse_datetime(texto)
        if data is None:
            return texto
        if timezone.is_aware(data):
            data = timezone.localtime(data)
        return data.strftime("%d/%m/%Y %H:%M:%S")
    data = dateparse.parse_date(texto[:10])
    return data.strftime("%d/%m/%Y") if data else texto


def legivel(modelo, nome, valor):
    """Texto do valor bruto do log/retrato para a tela."""
    if _vazio(valor):
        return VAZIO
    encontrado = campo(modelo, nome)
    if encontrado is None:
        return _texto(valor)
    if isinstance(encontrado, models.BooleanField):
        return "Sim" if str(valor).lower() in ("true", "1") else "Nao"
    if encontrado.many_to_one or encontrado.one_to_one:
        return _relacionado(encontrado, valor)
    if isinstance(encontrado, (models.DateTimeField, models.DateField)):
        return _data(encontrado, valor)
    if encontrado.choices:
        return str(dict(encontrado.flatchoices).get(valor, valor))
    return _texto(valor)


def mudancas(modelo, changes):
    """[(rotulo, antes, depois)] do changes do auditlog, na ordem dos campos do model."""
    ordem = {c.name: i for i, c in enumerate(modelo._meta.fields)} if modelo else {}
    linhas = []
    for nome in sorted(changes or {}, key=lambda n: (ordem.get(n, 999), n)):
        valor = changes[nome]
        if isinstance(valor, dict):  # muitos-para-muitos: {"type": "m2m", "objects": [...]}
            operacao = {"add": "adicionou", "delete": "removeu"}.get(valor.get("operation"), "")
            objetos = ", ".join(map(str, valor.get("objects", [])))
            linhas.append((rotulo(modelo, nome), operacao, objetos))
            continue
        antes, depois = (list(valor) + [None, None])[:2]
        linhas.append((rotulo(modelo, nome), legivel(modelo, nome, antes),
                       legivel(modelo, nome, depois)))
    return linhas


def retrato(modelo, dados):
    """[(rotulo, valor)] do registro inteiro (serialized_data do auditlog)."""
    campos = (dados or {}).get("fields") or {}
    ordem = {c.name: i for i, c in enumerate(modelo._meta.fields)} if modelo else {}
    return [(rotulo(modelo, nome), legivel(modelo, nome, campos[nome]))
            for nome in sorted(campos, key=lambda n: (ordem.get(n, 999), n))]
