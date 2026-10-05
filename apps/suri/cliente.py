"""Transporte HTTP da API do Suri Shop (by Totvs); nenhuma regra de negocio aqui.

    cliente = SuriClient(configuracao)        # dominio_loja = endpoint do chatbot
    cliente.get("shop/categories")
    for produto in cliente.produtos():        # pagina pelo token da resposta
        ...

Endpoint e token ficam no Portal do Suri > Configuracoes. Autentica com
"Authorization: Bearer <token>". A resposta vem num envelope
{"success", "data", "error", "errorCode"}: success false vira SuriErro.

Numero do JSON e lido como Decimal (parse_float): preco nunca passa por float.
Na ida, o Decimal vira numero JSON com o texto exato dele (`_json`).
"""

import json
import re
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

POR_PAGINA = 100
# Decimal vai como texto marcado e a marca (com as aspas) sai depois do dumps: o numero
# fica no JSON exatamente como o Decimal ("19.90" -> 19.90).
_MARCA = "#decimal#"
_NUMERO_MARCADO = re.compile(r'"#decimal#(-?\d+(?:\.\d+)?)"')


class SuriErro(RuntimeError):
    def __init__(self, mensagem, status=None, codigo=""):
        super().__init__(mensagem)
        self.status, self.codigo = status, codigo


def _marcar(valor):
    if isinstance(valor, Decimal):
        return f"{_MARCA}{valor}"
    if isinstance(valor, dict):
        return {chave: _marcar(v) for chave, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [_marcar(v) for v in valor]
    return valor


def _json(corpo):
    return _NUMERO_MARCADO.sub(r"\1", json.dumps(_marcar(corpo), ensure_ascii=False)).encode()


class SuriClient:
    def __init__(self, configuracao, timeout=30):
        self.configuracao = configuracao
        self.timeout = timeout
        self.base = f"{configuracao.dominio_loja.rstrip('/')}/api/"
        self.token = configuracao.token_acesso

    def requisitar(self, metodo, caminho, corpo=None):
        dados = _json(corpo) if corpo is not None else None
        requisicao = Request(f"{self.base}{caminho.lstrip('/')}", data=dados, method=metodo,
                             headers={"Content-Type": "application/json",
                                      "Accept": "application/json", "User-Agent": "StarHub/1.0",
                                      "Authorization": f"Bearer {self.token}"})
        try:
            with urlopen(requisicao, timeout=self.timeout) as resposta:
                envelope = json.loads(resposta.read().decode() or "null", parse_float=Decimal)
        except HTTPError as erro:
            raise _erro_http(erro) from erro
        except (URLError, TimeoutError, json.JSONDecodeError) as erro:
            raise SuriErro(f"Nao foi possivel falar com o Suri: {erro}") from erro
        if isinstance(envelope, dict) and envelope.get("success") is False:
            raise SuriErro(f"Suri recusou: {envelope.get('error') or envelope}",
                           codigo=str(envelope.get("errorCode") or ""))
        if isinstance(envelope, dict) and "success" in envelope:
            return envelope.get("data", envelope.get("value"))
        return envelope

    def get(self, caminho):
        return self.requisitar("GET", caminho)

    def post(self, caminho, corpo):
        return self.requisitar("POST", caminho, corpo)

    def put(self, caminho, corpo=None):
        return self.requisitar("PUT", caminho, corpo if corpo is not None else {})

    def delete(self, caminho):
        return self.requisitar("DELETE", caminho)

    def produtos(self):
        """Todos os produtos: a pagina seguinte vem pelo `token` da anterior."""
        token = None
        while True:
            pagina = self.post("shop/products/list", {"perPage": POR_PAGINA, "pageToken": token})
            yield from pagina.get("data") or []
            token = pagina.get("token")
            if not pagina.get("hasMore") or not token:
                return

    def pedidos(self, desde=None):
        """Pedidos por pagina numerada; sem `desde` o Suri devolve os ultimos 30 dias."""
        pagina = 1
        while True:
            filtro = {"Page": pagina, "PerPage": POR_PAGINA}
            if desde:
                filtro["CreatedDate"] = desde
            resposta = self.post("shop/orders", filtro)
            yield from resposta.get("data") or []
            if not resposta.get("hasMore") or not resposta.get("data"):
                return
            pagina += 1


def _erro_http(erro):
    detalhe = erro.read().decode(errors="replace")[:500]
    try:
        corpo = json.loads(detalhe)
    except json.JSONDecodeError:
        corpo = {}
    mensagem = (corpo.get("error") or corpo.get("message") or detalhe) if isinstance(
        corpo, dict) else detalhe
    dica = {401: " Confira o token em Integracoes > Suri Shop (Portal do Suri > "
                 "Configuracoes).",
            404: " Confira o endpoint do chatbot (Portal do Suri > Configuracoes)."}
    return SuriErro(f"Suri respondeu HTTP {erro.code}: {mensagem}.{dica.get(erro.code, '')}",
                    status=erro.code)
