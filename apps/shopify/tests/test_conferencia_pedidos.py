"""Conferencia do beat no Shopify: a busca de pedidos leva a janela na query da GraphQL."""

from apps.shopify.cliente import ShopifyClient
from apps.shopify.sincronizar import sincronizar_loja

JANELA = {"inicio": "2026-11-09T11:00:00+00:00", "fim": "2026-11-09T12:05:00+00:00",
          "conferido_ate": "2026-11-09T12:00:00+00:00"}
BUSCA = "updated_at:>='2026-11-09T11:00:00Z' AND updated_at:<='2026-11-09T12:05:00Z'"


class ClienteFalso:
    def __init__(self, *_a, **_k):
        self.listados = []

    def contar(self, recurso):
        return 9999  # contagem da loja inteira: com janela nao pode valer

    def listar(self, recurso, busca=None):
        self.listados.append((recurso, busca))
        return iter([])


def test_sincronizacao_com_janela_busca_so_pedidos_alterados_nela(monkeypatch):
    cliente = ClienteFalso()
    monkeypatch.setattr("apps.shopify.sincronizar.ShopifyClient", lambda *_a, **_k: cliente)

    class Config:
        def habilitado(self, *_):
            return True

    mensagem = sincronizar_loja(Config(), lambda *_: None, recursos=["pedidos"], janela=JANELA)

    assert cliente.listados == [("pedidos", BUSCA)]
    assert mensagem.startswith("0 itens")


def test_cliente_manda_a_busca_como_variavel_da_consulta_de_pedidos(monkeypatch):
    """Sem o $query declarado a Shopify recusa a variavel e a conferencia inteira cai."""
    chamadas = []

    def graphql(_self, query, variables=None):
        chamadas.append((query, variables))
        return {"orders": {"nodes": [], "pageInfo": {"hasNextPage": False}}}

    monkeypatch.setattr(ShopifyClient, "graphql", graphql)
    cliente = ShopifyClient.__new__(ShopifyClient)

    list(cliente.listar("pedidos", busca=BUSCA))

    query, variaveis = chamadas[0]
    assert "$query: String" in query and "query: $query" in query
    assert variaveis == {"cursor": None, "query": BUSCA}


def test_listar_sem_busca_nao_manda_a_variavel(monkeypatch):
    chamadas = []
    monkeypatch.setattr(ShopifyClient, "graphql", lambda _s, q, v=None: chamadas.append(v) or {
        "collections": {"nodes": [], "pageInfo": {"hasNextPage": False}}})

    list(ShopifyClient.__new__(ShopifyClient).listar("categorias"))

    assert chamadas == [{"cursor": None}]
