"""Repassa a requisicao de pedido que o ERP fez na API Woo do hub para a loja WooCommerce.

    status, corpo, cabecalhos = encaminhar(configuracao, "GET", "wc/v3/orders",
                                           "status=processing&page=2", b"", "")

Mesma rota (depois de /wp-json/), mesma query e mesmo corpo; quem autentica na loja e a
chave da configuracao (ck_/cs_), nunca a do ERP. A resposta volta como veio: status,
JSON e os cabecalhos de paginacao, inclusive erro (o ERP ve o erro da loja). Sem
resposta da loja (rede, tempo): 502 no formato de erro do Woo.

Sincrono de proposito: o ERP espera a resposta da loja na mesma requisicao.
"""

import base64
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)
TEMPO = 30
REPASSADOS = ("Content-Type", "X-WP-Total", "X-WP-TotalPages", "Link")
# A credencial do ERP na API do hub nao vai para a loja (la vale a da configuracao).
DO_HUB = {"consumer_key", "consumer_secret", "oauth_consumer_key", "oauth_signature",
          "oauth_signature_method", "oauth_nonce", "oauth_timestamp", "oauth_version"}


def _query(query, credencial=None):
    pares = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k not in DO_HUB]
    return urlencode(pares + list((credencial or {}).items()))


def _pedir(configuracao, metodo, caminho, query, corpo, tipo, na_query):
    base = f"{configuracao.dominio_loja.rstrip('/')}/wp-json/{caminho.lstrip('/')}"
    credencial = {"consumer_key": configuracao.token_acesso,
                  "consumer_secret": configuracao.segredo_app} if na_query else None
    consulta = _query(query, credencial)
    cabecalhos = {"Accept": "application/json", "User-Agent": "StarHub/1.0"}
    if tipo:
        cabecalhos["Content-Type"] = tipo
    if not na_query:
        chave = f"{configuracao.token_acesso}:{configuracao.segredo_app}"
        cabecalhos["Authorization"] = f"Basic {base64.b64encode(chave.encode()).decode()}"
    requisicao = Request(f"{base}?{consulta}" if consulta else base, data=corpo or None,
                         method=metodo, headers=cabecalhos)
    try:
        with urlopen(requisicao, timeout=TEMPO) as resposta:
            return resposta.status, resposta.read(), resposta.headers
    except HTTPError as erro:
        return erro.code, erro.read(), erro.headers


def _link(valor, configuracao, base_hub):
    """O Link aponta para a loja: troca pelo endereco do hub, por onde o ERP pagina."""
    return valor.replace(f"{configuracao.dominio_loja.rstrip('/')}/wp-json/", base_hub)


def indisponivel(erro):
    corpo = {"code": "starhub_loja_indisponivel",
             "message": f"A loja WooCommerce nao respondeu ({erro}). Tente de novo; se "
                        "continuar, confira o endereco da loja em Integracoes > WooCommerce.",
             "data": {"status": 502}}
    return 502, json.dumps(corpo).encode(), {"Content-Type": "application/json"}


def encaminhar(configuracao, metodo, caminho, query, corpo, tipo, base_hub=""):
    """(status, corpo em bytes, {cabecalho: valor}) da resposta da loja."""
    inicio = time.monotonic()
    try:
        status, bruto, cabecalhos = _pedir(configuracao, metodo, caminho, query, corpo, tipo,
                                           na_query=False)
        if status == 401:
            # Hospedagem que descarta o Authorization: a chave vai na query, como no cliente.
            status, bruto, cabecalhos = _pedir(configuracao, metodo, caminho, query, corpo,
                                               tipo, na_query=True)
    except (URLError, TimeoutError, OSError) as erro:
        logger.warning("Encaminhar %s %s: loja sem resposta: %s", metodo, caminho, erro)
        return indisponivel(erro)
    saida = {nome: cabecalhos.get(nome) for nome in REPASSADOS if cabecalhos.get(nome)}
    if "Link" in saida and base_hub:
        saida["Link"] = _link(saida["Link"], configuracao, base_hub)
    logger.info("Encaminhado %s %s -> loja HTTP %s em %.2fs", metodo, caminho, status,
                time.monotonic() - inicio)
    return status, bruto, saida
