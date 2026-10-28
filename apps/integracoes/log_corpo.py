"""Corpo de webhook e de API recebida no log do terminal, para validar integracao em prod.

    logger.info("... corpo=%s", log_corpo.corpo(request.body))
    logger.info("... chaves=%s", log_corpo.estrutura(dados))

O corpo traz dado de cliente (nome, endereco, telefone): so aparece com DEBUG ou com
LOG_CORPO_INTEGRACOES=1 no .env, ligado enquanto se investiga e desligado depois.
Credencial (token, senha, segredo) sai mascarada mesmo com a chave ligada.
`estrutura` mostra so as chaves e o tipo de cada valor: sem dado de cliente, pode ir
sempre para o log e ja diz se o campo esperado veio com outro nome.
"""

import json

from django.conf import settings

LIMITE = 20_000
SEGREDOS = ("token", "senha", "password", "secret", "segredo", "authorization", "api_key",
            "apikey", "hmac")
MASCARA = "***"


def ligado():
    return bool(settings.DEBUG or getattr(settings, "LOG_CORPO_INTEGRACOES", False))


def _mascarar(valor):
    if isinstance(valor, dict):
        return {chave: MASCARA if any(s in str(chave).lower() for s in SEGREDOS)
                else _mascarar(item) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_mascarar(item) for item in valor]
    return valor


def corpo(bruto):
    """Texto de uma linha para o log; so o tamanho quando o log de corpo esta desligado."""
    if isinstance(bruto, str):
        bruto = bruto.encode()
    bruto = bruto or b""
    if not ligado():
        return f"<{len(bruto)} bytes; LOG_CORPO_INTEGRACOES=1 no .env mostra o corpo>"
    try:
        texto = json.dumps(_mascarar(json.loads(bruto)), ensure_ascii=False, default=str)
    except (json.JSONDecodeError, UnicodeDecodeError):
        texto = bruto.decode(errors="replace")
    if len(texto) > LIMITE:
        return f"{texto[:LIMITE]}... (cortado: {len(texto)} caracteres)"
    return texto


def estrutura(dados, nivel=5):
    """Chaves do JSON com o tipo de cada valor, sem os valores. Lista mostra o 1o item."""
    if isinstance(dados, dict):
        if not nivel:
            return "{...}"
        return {chave: estrutura(item, nivel - 1) for chave, item in dados.items()}
    if isinstance(dados, list):
        return [estrutura(dados[0], nivel - 1)] if dados and nivel else []
    if dados is None:
        return None
    return "vazio" if dados == "" else type(dados).__name__
