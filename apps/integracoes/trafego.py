"""Requisicao recebida e resposta dada, guardadas na tarefa para a tela de Tarefas.

    parametros["requisicao"] = requisicao(request, corpo)   # webhook ou API recebida
    parametros["resposta"] = resposta(202)                   # o que o hub respondeu

Cabecalho com credencial (Authorization, cookie, chave) nao e guardado: a tela de
tarefas e lida por quem nao tem acesso as chaves. Corpo grande e cortado em
LIMITE caracteres; a tela avisa que esta cortado.
"""

import json

LIMITE = 200_000
SEGREDOS = ("authorization", "cookie", "x-csrftoken", "x-api-key", "consumer")
CORTADO = "\n... (cortado: o corpo passa de 200 mil caracteres)"


def _cabecalhos(cabecalhos):
    return {nome: valor for nome, valor in (cabecalhos or {}).items()
            if not any(s in nome.lower() for s in SEGREDOS)}


def corpo_guardavel(bruto):
    """JSON vira objeto (a tela formata); texto fica texto; grande e cortado."""
    if isinstance(bruto, bytes):
        bruto = bruto.decode(errors="replace")
    if not isinstance(bruto, str):
        return bruto
    if len(bruto) > LIMITE:
        return bruto[:LIMITE] + CORTADO
    try:
        return json.loads(bruto) if bruto.strip() else ""
    except json.JSONDecodeError:
        return bruto


def requisicao(request, corpo=None):
    """Retrato da requisicao recebida; `corpo` None = o corpo ja fica em outro lugar."""
    retrato = {"metodo": request.method, "caminho": request.path,
               "query": _sem_credencial(request.GET),
               "cabecalhos": _cabecalhos(dict(request.headers))}
    if corpo is not None:
        retrato["corpo"] = corpo_guardavel(corpo)
    return retrato


def _sem_credencial(query):
    return {k: v for k, v in query.items() if not any(s in k.lower() for s in SEGREDOS)}


def resposta(status, corpo=None, cabecalhos=None):
    saida = {"status": status}
    if cabecalhos:
        saida["cabecalhos"] = _cabecalhos(cabecalhos)
    if corpo is not None:
        saida["corpo"] = corpo_guardavel(corpo)
    return saida


def _legivel(valor):
    if valor in (None, ""):
        return ""
    if isinstance(valor, str):
        return valor
    return json.dumps(valor, ensure_ascii=False, indent=2, default=str)


def para_tela(parametros):
    """{"requisicao": {...}, "resposta": {...}} prontos para o template, ou {}."""
    parametros = parametros or {}
    pedida, dada = parametros.get("requisicao"), parametros.get("resposta")
    if not pedida and not dada:
        return {}
    pedida = dict(pedida or {})
    if "corpo" not in pedida:
        # Webhook: o corpo ja esta guardado para o Retomar (parametros["reenvio"]).
        pedida["corpo"] = (parametros.get("reenvio") or {}).get("dados")
    query = "&".join(f"{k}={v}" for k, v in (pedida.get("query") or {}).items())
    caminho = f"{pedida.get('caminho', '')}{'?' + query if query else ''}"
    return {
        "requisicao": {"linha": f"{pedida.get('metodo', '')} {caminho}".strip(),
                       "cabecalhos": sorted((pedida.get("cabecalhos") or {}).items()),
                       "corpo": _legivel(pedida.get("corpo"))} if pedida else None,
        "resposta": {"status": (dada or {}).get("status"),
                     "linha": f"HTTP {(dada or {}).get('status')}",
                     "cabecalhos": sorted(((dada or {}).get("cabecalhos") or {}).items()),
                     "corpo": _legivel((dada or {}).get("corpo"))} if dada else None,
    }
