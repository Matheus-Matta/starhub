"""Encaminhamento de ponta a ponta: um servidor HTTP local faz o papel da loja Woo.

Os testes de test_encaminhar_pedidos.py trocam a ida HTTP por uma funcao falsa; aqui
o urllib vai de verdade (Basic Auth, volta para a query no 401, cabecalhos, corpo).
"""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.woocommerce.tests.loja_falsa import configuracao

pytestmark = pytest.mark.django_db
BASIC = "Basic " + base64.b64encode(b"ck_teste:cs_teste").decode()


class LojaHttp(BaseHTTPRequestHandler):
    recebidas = []
    aceita_basic = True

    def _responder(self):
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(tamanho) if tamanho else b""
        partes = urlsplit(self.path)
        query = parse_qs(partes.query)
        self.recebidas.append({"metodo": self.command, "caminho": partes.path, "query": query,
                               "auth": self.headers.get("Authorization"), "corpo": corpo})
        pela_query = query.get("consumer_key") == ["ck_teste"]
        if not ((self.aceita_basic and self.headers.get("Authorization") == BASIC) or pela_query):
            self._json(401, {"code": "woocommerce_rest_cannot_view", "message": "sem chave"})
            return
        if partes.path.endswith("/orders/999"):
            self._json(404, {"code": "woocommerce_rest_shop_order_invalid_id",
                             "message": "ID invalido.", "data": {"status": 404}})
            return
        self._json(200, [{"id": 12, "status": "processing"}],
                   {"X-WP-Total": "40", "X-WP-TotalPages": "2"})

    def _json(self, status, dados, extra=None):
        bruto = json.dumps(dados).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=UTF-8")
        for nome, valor in (extra or {}).items():
            self.send_header(nome, valor)
        self.send_header("Content-Length", str(len(bruto)))
        self.end_headers()
        self.wfile.write(bruto)

    do_GET = do_PUT = do_POST = _responder

    def log_message(self, *args):
        pass


@pytest.fixture
def loja_http(conta):
    LojaHttp.recebidas, LojaHttp.aceita_basic = [], True
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), LojaHttp)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    cfg = configuracao(conta)
    ConfiguracaoIntegracao.objects.filter(pk=cfg.pk).update(
        dominio_loja=f"http://127.0.0.1:{servidor.server_port}", encaminhar_pedidos=True)
    yield LojaHttp
    servidor.shutdown()
    servidor.server_close()


def test_lista_vai_com_a_chave_da_loja_e_volta_com_a_paginacao(api, loja_http):
    resposta = api.get("/wp-json/wc/v3/orders?status=processing&per_page=20")

    pedido = loja_http.recebidas[0]
    assert pedido["caminho"] == "/wp-json/wc/v3/orders"
    assert pedido["query"] == {"status": ["processing"], "per_page": ["20"]}
    assert pedido["auth"] == BASIC, "a loja recebe a chave da configuracao, nao a do ERP"
    assert resposta.status_code == 200
    assert json.loads(resposta.content) == [{"id": 12, "status": "processing"}]
    assert (resposta["X-WP-Total"], resposta["X-WP-TotalPages"]) == ("40", "2")


def test_atualizacao_leva_o_corpo_inteiro(api, loja_http):
    api.put("/wp-json/wc/v3/orders/12", {"status": "completed", "meta_data": []},
            format="json")

    pedido = loja_http.recebidas[0]
    assert pedido["metodo"] == "PUT" and pedido["caminho"] == "/wp-json/wc/v3/orders/12"
    assert json.loads(pedido["corpo"]) == {"status": "completed", "meta_data": []}


def test_hospedagem_sem_authorization_cai_para_a_chave_na_query(api, loja_http):
    loja_http.aceita_basic = False

    resposta = api.get("/wp-json/wc/v3/orders")

    assert [p["auth"] is not None for p in loja_http.recebidas] == [True, False]
    assert loja_http.recebidas[1]["query"]["consumer_key"] == ["ck_teste"]
    assert resposta.status_code == 200


def test_erro_da_loja_volta_igual_e_a_tarefa_fica_como_falhou(api, loja_http):
    resposta = api.get("/wp-json/wc/v3/orders/999")

    assert resposta.status_code == 404
    assert json.loads(resposta.content)["code"] == "woocommerce_rest_shop_order_invalid_id"
    tarefa = ExecucaoIntegracao.objects.get(tipo=ExecucaoIntegracao.Tipo.ENCAMINHAR)
    assert tarefa.status == ExecucaoIntegracao.Status.FALHOU
    assert tarefa.parametros["resposta"]["status"] == 404
