"""Sincronizacao de produtos em paginas de 10, ate a ultima pagina.

Pagina de 3 gastava 3x mais chamadas; pagina de 10 so cabe nos 1000 pontos com o
lote enxuto, e o que o lote corta (variantes, colecoes, fotos) e completado pela
consulta de um produto. Foto cortada antes nao era completada: o produto com mais
fotos que o lote ficava sem as ultimas no hub.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.shopify.cliente import ShopifyClient
from apps.shopify.consultas import CONSULTAS
from apps.shopify.consultas_produtos import CONSULTA_PRODUTO
from apps.shopify.contexto import usando_configuracao
from apps.shopify.produtos_busca import completar
from apps.shopify.tests.custo_graphql import custo
from apps.shopify.tests.test_imagens_webhook import _configuracao
from apps.shopify.tests.test_produto_completo import GID, LojaFalsa, node

LOTE = CONSULTAS["produtos"][1]


def _compacta(query):
    return " ".join(query.split())


def test_lote_pede_10_produtos_por_pagina_dentro_de_1000_pontos():
    """Acima de 1000 pontos o Shopify recusa a consulta e a sincronizacao inteira cai."""
    assert "products(first: 10, after: $cursor)" in _compacta(LOTE)
    assert custo(LOTE) <= 1000


def test_consulta_de_um_produto_cabe_em_1000_pontos():
    assert custo(CONSULTA_PRODUTO) <= 1000


def test_lote_e_busca_por_id_avisam_quando_as_fotos_vem_cortadas():
    """Sem pageInfo em media nao ha como saber que faltou foto."""
    for query in (LOTE, CONSULTA_PRODUTO):
        assert "status image { url altText } } } pageInfo { hasNextPage } }" in _compacta(query)


@pytest.mark.django_db
def test_fotos_cortadas_no_lote_buscam_o_produto_inteiro(conta):
    cortado = node(media={"nodes": [], "pageInfo": {"hasNextPage": True}})
    loja = LojaFalsa(node(handle="inteiro"))
    with patch("apps.shopify.produtos_busca.ShopifyClient", loja), \
            usando_configuracao(_configuracao(conta)):
        completo = completar(cortado)

    assert loja.pedidos == [{"id": GID}]
    assert completo["handle"] == "inteiro"


def _pagina(ids, proximo):
    return {"products": {"nodes": [{"id": i} for i in ids],
                         "pageInfo": {"hasNextPage": proximo is not None,
                                      "endCursor": proximo}}}


def test_listar_segue_o_cursor_ate_a_ultima_pagina():
    """Parar na primeira pagina deixaria todo produto depois do 10o fora do hub."""
    paginas = iter([_pagina(range(10), "c1"), _pagina(range(10, 20), "c2"),
                    _pagina([20, 21], None)])
    cursores = []

    def graphql(_self, query, variables=None):
        cursores.append(variables["cursor"])
        return next(paginas)

    cliente = ShopifyClient(SimpleNamespace(dominio_loja="x.myshopify.com",
                                            versao_api="2026-07"))
    with patch.object(ShopifyClient, "graphql", graphql):
        ids = [produto["id"] for produto in cliente.listar("produtos")]

    assert ids == list(range(22))
    assert cursores == [None, "c1", "c2"]
