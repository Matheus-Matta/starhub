"""Transporte HTTP da API REST v3 do WooCommerce; nenhuma regra de negocio aqui.

    cliente = WooClient(configuracao)
    cliente.get("products/15")
    for produto in cliente.listar("products"):  # pagina sozinho (X-WP-TotalPages)
        ...
    cliente.put("products/15", {"regular_price": "19.90"})

Autentica com a chave da API (ck_/cs_) por Basic Auth. Hospedagem com Apache costuma
descartar o cabecalho Authorization: no primeiro 401 o cliente passa a mandar a chave
na query string (o metodo que a propria documentacao do Woo indica nesse caso).
"""

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

POR_PAGINA = 100  # o maximo que a API do Woo aceita


class WooErro(RuntimeError):
    def __init__(self, mensagem, status=None, codigo=""):
        super().__init__(mensagem)
        self.status, self.codigo = status, codigo


class WooClient:
    def __init__(self, configuracao, timeout=30):
        self.configuracao = configuracao
        self.timeout = timeout
        self.base = f"{configuracao.dominio_loja.rstrip('/')}/wp-json/wc/v3/"
        self.chave = configuracao.token_acesso
        self.segredo = configuracao.segredo_app
        self._na_query = False

    def _url(self, caminho, params):
        params = dict(params or {})
        if self._na_query:
            params |= {"consumer_key": self.chave, "consumer_secret": self.segredo}
        consulta = f"?{urlencode(params, doseq=True)}" if params else ""
        return f"{self.base}{caminho.lstrip('/')}{consulta}"

    def _cabecalhos(self):
        cabecalhos = {"Content-Type": "application/json", "Accept": "application/json",
                      "User-Agent": "StarHub/1.0"}
        if not self._na_query:
            credencial = base64.b64encode(f"{self.chave}:{self.segredo}".encode()).decode()
            cabecalhos["Authorization"] = f"Basic {credencial}"
        return cabecalhos

    def requisitar(self, metodo, caminho, params=None, corpo=None):
        """(dados, cabecalhos da resposta); WooErro com a mensagem do Woo se falhar."""
        dados = json.dumps(corpo).encode() if corpo is not None else None
        requisicao = Request(self._url(caminho, params), data=dados, method=metodo,
                             headers=self._cabecalhos())
        try:
            with urlopen(requisicao, timeout=self.timeout) as resposta:
                texto = resposta.read().decode() or "null"
                return json.loads(texto), resposta.headers
        except HTTPError as erro:
            if erro.code == 401 and not self._na_query:
                self._na_query = True
                return self.requisitar(metodo, caminho, params, corpo)
            raise _erro_http(erro) from erro
        except (URLError, TimeoutError, json.JSONDecodeError) as erro:
            raise WooErro(f"Nao foi possivel falar com a loja WooCommerce: {erro}") from erro

    def get(self, caminho, **params):
        return self.requisitar("GET", caminho, params)[0]

    def post(self, caminho, corpo):
        return self.requisitar("POST", caminho, corpo=corpo)[0]

    def put(self, caminho, corpo):
        return self.requisitar("PUT", caminho, corpo=corpo)[0]

    def delete(self, caminho):
        # force=true: sem ele produto e pedido vao para a lixeira e o resto recusa.
        return self.requisitar("DELETE", caminho, {"force": "true"})[0]

    def listar(self, caminho, **params):
        pagina = 1
        while True:
            itens, cabecalhos = self.requisitar(
                "GET", caminho, {**params, "per_page": POR_PAGINA, "page": pagina})
            yield from itens or []
            total = int(cabecalhos.get("X-WP-TotalPages") or 1)
            if pagina >= total or not itens:
                return
            pagina += 1

    def contar(self, caminho, **params):
        """Total de itens (X-WP-Total) para a barra de progresso; None se nao der."""
        try:
            _, cabecalhos = self.requisitar("GET", caminho, {**params, "per_page": 1})
        except WooErro:
            return None
        total = cabecalhos.get("X-WP-Total")
        return int(total) if total is not None else None


def _erro_http(erro):
    detalhe = erro.read().decode(errors="replace")[:500]
    try:
        corpo = json.loads(detalhe)
    except json.JSONDecodeError:
        corpo = {}
    codigo, mensagem = corpo.get("code", ""), corpo.get("message") or detalhe
    dica = {401: " Confira a chave e o segredo da API (ck_/cs_) em Integracoes > WooCommerce.",
            403: " A chave da API precisa de permissao de leitura e escrita.",
            404: ""}.get(erro.code, "")
    return WooErro(f"WooCommerce respondeu HTTP {erro.code}: {mensagem}.{dica}",
                   status=erro.code, codigo=codigo)
