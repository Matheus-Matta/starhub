"""Falha por item de uma tarefa de integracao: o que deu erro, em qual registro e por que.

Formato de cada item (lista em ExecucaoIntegracao.falhas):
  {"recurso": "produtos", "id": "<pk no hub>", "descricao": "Camiseta (SKU CAM-1)",
   "id_externo": "<id no marketplace>", "motivo": "<texto para o operador>"}
Campo desconhecido fica "" (nunca ausente): o template e o teste leem sempre as cinco.
"""

import re
from urllib.error import URLError

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.integracoes.models import ExecucaoIntegracao

# Uma exportacao de catalogo grande com a API fora geraria milhares de linhas iguais;
# o que passa disso so entra na contagem da mensagem.
MAX_FALHAS = 200

_HTTP = re.compile(r"HTTP (\d{3})")
_POR_HTTP = {
    "401": "O marketplace recusou as credenciais (HTTP 401); confira o token na configuracao.",
    "403": "O marketplace recusou as credenciais (HTTP 403): falta permissao no app da loja.",
    "404": "O marketplace nao achou o registro (HTTP 404); ele pode ter sido apagado la.",
    "429": "O marketplace limitou as chamadas (HTTP 429); rode de novo em alguns minutos.",
}


def item(recurso, motivo, id="", descricao="", id_externo=""):  # noqa: A002 - nome do campo
    return {
        "recurso": str(recurso or ""),
        "id": str(id or ""),
        "descricao": str(descricao or "")[:200],
        "id_externo": str(id_externo or ""),
        "motivo": str(motivo or "")[:1000],
    }


def descrever(obj):
    """Nome do registro para o operador achar o item: str() do model + SKU se houver."""
    if obj is None:
        return ""
    texto = str(obj)
    sku = getattr(obj, "sku", "") or ""
    if sku and sku not in texto:
        texto = f"{texto} (SKU {sku})"
    return texto


def motivo_legivel(erro):
    """Mensagem do erro com a traducao do que o operador deve fazer, quando conhecido."""
    texto = str(erro).strip()
    if isinstance(erro, IntegrityError):
        return ("Ja existe outro registro com o mesmo codigo, SKU ou e-mail no hub; "
                f"corrija o duplicado e rode de novo. Detalhe: {texto}")
    if isinstance(erro, ValidationError):
        return "Dado invalido: " + "; ".join(erro.messages)
    if isinstance(erro, (TimeoutError, URLError)):
        return f"O marketplace nao respondeu a tempo; rode de novo mais tarde. Detalhe: {texto}"
    codigo = _HTTP.search(texto)
    if codigo and codigo.group(1) in _POR_HTTP:
        return f"{_POR_HTTP[codigo.group(1)]} Detalhe: {texto}"
    if codigo and codigo.group(1).startswith("5"):
        return f"O marketplace esta com erro interno; rode de novo mais tarde. Detalhe: {texto}"
    return texto or type(erro).__name__


def status_final(ok, falhas):
    """Sem falha: concluida. Com falha e nada certo: falhou. O resto: concluida com falhas."""
    if not falhas:
        return ExecucaoIntegracao.Status.CONCLUIDA
    if not ok:
        return ExecucaoIntegracao.Status.FALHOU
    return ExecucaoIntegracao.Status.CONCLUIDA_COM_FALHAS
