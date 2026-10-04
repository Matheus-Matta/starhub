"""Progresso da sincronizacao por item: a barra anda com "Produtos: 350 de 1200"."""

from types import SimpleNamespace

import pytest

from apps.shopify import sincronizar
from apps.shopify.cliente import ShopifyClient, ShopifyErro
from apps.shopify.tests.test_sincronizar import _configuracao

CONFIG = SimpleNamespace(dominio_loja="loja.myshopify.com", versao_api="2026-07", token_acesso="x")


def _cliente(respostas):
    cliente = ShopifyClient(CONFIG)
    chamadas = []

    def graphql(query, variables=None):
        chamadas.append(query)
        resposta = respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    cliente.graphql = graphql
    return cliente, chamadas


def test_contar_pede_o_numero_exato():
    """O padrao do productsCount para em 10.000: loja grande ficaria com a barra errada."""
    cliente, chamadas = _cliente([{"productsCount": {"count": 1234}}])
    assert cliente.contar("produtos") == 1234
    assert "productsCount(limit: null)" in chamadas[0]


def test_contar_tenta_sem_limit_quando_o_campo_nao_aceita():
    cliente, chamadas = _cliente([ShopifyErro("argumento limit desconhecido"),
                                  {"customersCount": {"count": 80}}])
    assert cliente.contar("clientes") == 80
    assert "customersCount {" in chamadas[1]


def test_contar_sem_resposta_ou_sem_contagem_devolve_none():
    """Contagem e so para a barra: falhar nao pode derrubar a sincronizacao."""
    cliente, _ = _cliente([ShopifyErro("fora"), ShopifyErro("fora")])
    assert cliente.contar("produtos") is None
    cliente, chamadas = _cliente([])
    assert cliente.contar("cupons") is None and chamadas == []


@pytest.mark.django_db
def test_barra_anda_por_item_somando_os_recursos(monkeypatch):
    """Com um recurso so a barra ficava em 0 de 1 ate o fim e pulava para 100%."""
    configuracao = _configuracao(("produtos", "get"), ("clientes", "get"))
    configuracao.save()
    itens = {"produtos": 25, "clientes": 5}
    passos = []

    class ClienteFalso:
        def __init__(self, _configuracao):
            pass

        def contar(self, recurso):
            return itens[recurso]

        def listar(self, recurso):
            return iter([{"id": n} for n in range(itens[recurso])])

    monkeypatch.setattr(sincronizar, "ShopifyClient", ClienteFalso)
    for recurso in itens:
        monkeypatch.setitem(sincronizar.SINCRONIZADORES, recurso, lambda dados: (dados, False))

    sincronizar.sincronizar_loja(configuracao, lambda *args: passos.append(args))

    assert (10, 30, "Produtos: 10 de 25") in passos
    assert (25, 30, "Produtos: 25 de 25") in passos
    assert passos[-1] == (30, 30, "Clientes: 5 de 5")
    feitos = [feito for feito, _, _ in passos]
    assert feitos == sorted(feitos), "a barra nunca pode voltar"


@pytest.mark.django_db
def test_loja_que_ganha_item_durante_a_busca_nao_passa_de_100(monkeypatch):
    configuracao = _configuracao(("produtos", "get"))
    configuracao.save()
    passos = []

    class ClienteFalso:
        def __init__(self, _configuracao):
            pass

        def contar(self, _recurso):
            return 10

        def listar(self, _recurso):
            return iter([{"id": n} for n in range(12)])

    monkeypatch.setattr(sincronizar, "ShopifyClient", ClienteFalso)
    monkeypatch.setitem(sincronizar.SINCRONIZADORES, "produtos", lambda dados: (dados, False))

    sincronizar.sincronizar_loja(configuracao, lambda *args: passos.append(args))

    assert all(feito <= total for feito, total, _ in passos)
    assert passos[-1][:2] == (12, 12)
