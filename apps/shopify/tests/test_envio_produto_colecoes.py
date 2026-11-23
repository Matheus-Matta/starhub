"""Categorias do produto no hub entram como colecoes do produto no Shopify.

O produto tinha 3 categorias no hub e chegava na loja sem colecao nenhuma: o envio de
categoria cria a colecao, mas nada ligava o produto a ela.
"""

import logging

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Categoria
from apps.shopify.tests.test_envio_produtos import (
    PRODUTO_GID,
    _enviador,
    _resposta_set,
    _simples,
)
from apps.shopify.tests.test_envio_produtos_atualizar import _respostas, _vincular

pytestmark = pytest.mark.django_db
OK = {"collectionAddProducts": {"collectionAddProducts": {"userErrors": []}}}


def _colecao(numero):
    return f"gid://shopify/Collection/{numero}"


def _categorias(produto, *vinculadas):
    """Uma categoria por item: numero da colecao na loja, ou None (sem vinculo)."""
    for posicao, numero in enumerate(vinculadas):
        categoria = Categoria.objects.create(nome=f"Cat {posicao}", slug=f"cat-{posicao}")
        produto.categorias.add(categoria)
        if numero:
            ExternalReference.objects.create(platform="shopify", entity_type="categorias",
                                             object_id=str(categoria.pk),
                                             external_id=_colecao(numero))


def _adicionadas(enviador):
    return [v for q, v in enviador.cliente.chamadas if "collectionAddProducts" in q]


def test_produto_novo_entra_nas_colecoes_das_suas_categorias(conta, caplog):
    produto, _variante = _simples()
    _categorias(produto, 10, 11, None)
    enviador = _enviador(conta, {
        "location": {"location": {"id": "gid://shopify/Location/1"}},
        "productSet": _resposta_set(1), **OK})

    with caplog.at_level(logging.WARNING):
        enviador.criar(produto)

    assert sorted(v["id"] for v in _adicionadas(enviador)) == [_colecao(10), _colecao(11)]
    assert all(v["productIds"] == [PRODUTO_GID] for v in _adicionadas(enviador))
    # A sem colecao na loja nao some em silencio: o log diz o que fazer.
    assert "Cat 2" in caplog.text and "Enviar > Categorias" in caplog.text


def test_update_so_adiciona_a_colecao_que_falta(conta):
    produto, variante = _simples()
    _vincular(variante, 1)
    _categorias(produto, 10, 11)
    respostas = _respostas()
    respostas["productUpdate"] = {"productUpdate": {"product": {
        "id": PRODUTO_GID, "collections": {"nodes": [{"id": _colecao(10)}]}},
        "userErrors": []}}
    enviador = _enviador(conta, {**respostas, **OK})

    enviador.atualizar(produto, PRODUTO_GID)

    assert [v["id"] for v in _adicionadas(enviador)] == [_colecao(11)]


def test_colecao_automatica_recusada_nao_barra_as_outras(conta):
    """Colecao por regra recusa produto posto a mao; o resto do envio segue."""
    produto, _variante = _simples()
    _categorias(produto, 10, 11)
    enviador = _enviador(conta, {
        "location": {"location": {"id": "gid://shopify/Location/1"}},
        "productSet": _resposta_set(1),
        "collectionAddProducts": {"collectionAddProducts": {"userErrors": [
            {"field": ["id"], "message": "Can't add products to a smart collection"}]}}})

    assert enviador.criar(produto) == PRODUTO_GID
    assert len(_adicionadas(enviador)) == 2
