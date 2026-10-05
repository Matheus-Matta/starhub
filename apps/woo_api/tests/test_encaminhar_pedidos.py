"""Modo "encaminhar pedidos a loja WooCommerce": a API do hub vira repasse da loja."""

import json

import pytest

from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.loja.models import Pedido
from apps.woocommerce.tests.loja_falsa import configuracao

pytestmark = pytest.mark.django_db


@pytest.fixture
def loja(monkeypatch):
    """Substitui a ida HTTP a loja: guarda o que foi pedido e devolve a resposta combinada."""
    chamadas = []
    resposta = {"status": 200, "corpo": b'[{"id": 77}]',
                "cabecalhos": {"Content-Type": "application/json; charset=UTF-8",
                               "X-WP-Total": "31", "X-WP-TotalPages": "4",
                               "Link": '<https://loja.test/wp-json/wc/v3/orders?page=2>; '
                                       'rel="next"'}}

    def pedir(cfg, metodo, caminho, query, corpo, tipo, na_query):
        chamadas.append({"metodo": metodo, "caminho": caminho, "query": query,
                         "corpo": corpo, "tipo": tipo, "na_query": na_query})
        return resposta["status"], resposta["corpo"], resposta["cabecalhos"]

    monkeypatch.setattr("apps.woocommerce.encaminhar._pedir", pedir)
    return chamadas, resposta


def _ligar(conta, ligado=True):
    cfg = configuracao(conta)
    ConfiguracaoIntegracao.objects.filter(pk=cfg.pk).update(encaminhar_pedidos=ligado)
    return cfg


def test_desligado_a_api_responde_com_os_pedidos_do_hub(api, conta, loja):
    _ligar(conta, ligado=False)

    resposta = api.get("/wp-json/wc/v3/orders")

    assert resposta.status_code == 200 and loja[0] == []


def test_ligado_repassa_a_mesma_rota_e_query_e_devolve_a_resposta_da_loja(api, conta, loja):
    _ligar(conta)

    resposta = api.get("/wp-json/wc/v3/orders?status=processing&page=1&consumer_key=ck_erp")

    chamada = loja[0][0]
    assert (chamada["metodo"], chamada["caminho"]) == ("GET", "wc/v3/orders")
    assert chamada["query"] == "status=processing&page=1&consumer_key=ck_erp"
    assert resposta.status_code == 200 and json.loads(resposta.content) == [{"id": 77}]
    assert (resposta["X-WP-Total"], resposta["X-WP-TotalPages"]) == ("31", "4")
    assert resposta["Link"].startswith("<http://testserver/wp-json/wc/v3/orders?page=2>")
    assert not Pedido.objects.exists()


def test_credencial_do_erp_nao_vai_para_a_loja(conta, monkeypatch):
    """A loja recebe a chave da configuracao; a do ERP fica no hub."""
    from apps.woocommerce.encaminhar import _query

    assert _query("status=x&consumer_key=ck_erp&consumer_secret=cs_erp") == "status=x"
    assert "ck_loja" in _query("a=1", {"consumer_key": "ck_loja"})


def test_atualizacao_leva_o_corpo_e_erro_da_loja_volta_igual(api, conta, loja):
    _ligar(conta)
    loja[1].update(status=400, corpo=b'{"code":"woocommerce_rest_invalid","message":"x"}',
                   cabecalhos={"Content-Type": "application/json"})

    resposta = api.put("/wp-json/wc/v3/orders/12", {"status": "completed"}, format="json")

    chamada = loja[0][0]
    assert chamada["metodo"] == "PUT" and json.loads(chamada["corpo"]) == {"status": "completed"}
    assert resposta.status_code == 400
    assert json.loads(resposta.content)["code"] == "woocommerce_rest_invalid"


def test_v1_tambem_encaminha_e_cada_chamada_vira_tarefa(api, conta, loja):
    _ligar(conta)

    api.get("/wp-json/wc/v1/orders/12")

    assert loja[0][0]["caminho"] == "wc/v1/orders/12"
    tarefa = ExecucaoIntegracao.objects.get(tipo=ExecucaoIntegracao.Tipo.ENCAMINHAR)
    assert tarefa.status == ExecucaoIntegracao.Status.CONCLUIDA
    assert tarefa.parametros["resposta"]["corpo"] == [{"id": 77}]
    assert "authorization" not in {k.lower() for k in tarefa.parametros["requisicao"]
                                   ["cabecalhos"]}


def test_loja_fora_do_ar_responde_502_no_formato_do_woo(api, conta, monkeypatch):
    _ligar(conta)

    def sem_rede(*_a, **_k):
        raise OSError("tempo esgotado")

    monkeypatch.setattr("apps.woocommerce.encaminhar._pedir", sem_rede)

    resposta = api.get("/wp-json/wc/v3/orders")

    assert resposta.status_code == 502
    assert json.loads(resposta.content)["code"] == "starhub_loja_indisponivel"


def test_produtos_nao_sao_encaminhados(api, conta, loja):
    _ligar(conta)

    api.get("/wp-json/wc/v3/products")

    assert loja[0] == []
