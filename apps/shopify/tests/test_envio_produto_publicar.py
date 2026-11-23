"""Produto criado do zero no Shopify sai publicado em todos os canais de venda.

O productSet cria o produto ACTIVE mas sem canal nenhum: ele nao aparecia na loja
virtual (nem no POS, Google, etc.) ate alguem marcar os canais a mao no admin da Shopify.
"""

import logging

import pytest

from apps.core.models import ExternalReference
from apps.shopify.tests.test_envio_produtos import (
    PRODUTO_GID,
    _enviador,
    _resposta_set,
    _simples,
)
from apps.shopify.tests.test_envio_produtos_atualizar import _respostas as respostas_update
from apps.shopify.tests.test_envio_produtos_atualizar import _vincular as vincular_variante

pytestmark = pytest.mark.django_db
CANAIS = {"publications": {"nodes": [
    {"id": "gid://shopify/Publication/1", "name": "Online Store"},
    {"id": "gid://shopify/Publication/2", "name": "Point of Sale"},
    {"id": "gid://shopify/Publication/3", "name": "Google & YouTube"},
]}}
LOCAL = {"location": {"id": "gid://shopify/Location/1"}}


def _publicacoes(enviador):
    return [v for q, v in enviador.cliente.chamadas if "publishablePublish" in q]


def test_produto_novo_e_publicado_em_todos_os_canais(conta):
    produto, _variante = _simples()
    enviador = _enviador(conta, {
        "location": LOCAL, "productSet": _resposta_set(1), "publications(": CANAIS,
        "publishablePublish": {"publishablePublish": {"userErrors": []}},
    })

    enviador.enviar("create", produto.pk)

    [variaveis] = _publicacoes(enviador)
    assert variaveis == {"id": PRODUTO_GID, "input": [
        {"publicationId": "gid://shopify/Publication/1"},
        {"publicationId": "gid://shopify/Publication/2"},
        {"publicationId": "gid://shopify/Publication/3"},
    ]}


def test_canal_recusado_nao_perde_o_vinculo_do_produto_ja_criado(conta, caplog):
    """O produto ja existe na loja quando a publicacao falha: sem o vinculo, o proximo
    envio criaria um segundo produto igual."""
    produto, _variante = _simples()
    enviador = _enviador(conta, {
        "location": LOCAL, "productSet": _resposta_set(1), "publications(": CANAIS,
        "publishablePublish": {"publishablePublish": {"userErrors": [
            {"field": ["input"], "message": "Access denied"}]}},
    })

    with caplog.at_level(logging.WARNING):
        assert enviador.enviar("create", produto.pk) == f"criado {PRODUTO_GID}"

    assert ExternalReference.objects.get(entity_type="produtos").external_id == PRODUTO_GID
    assert "write_publications" in caplog.text


def test_atualizar_nao_publica_de_novo(conta):
    """Canal tirado a mao na Shopify (ex.: fora do POS) nao volta a cada edicao no hub."""
    produto, variante = _simples()
    vincular_variante(variante, 1)
    enviador = _enviador(conta, {**respostas_update(), "publications(": CANAIS})

    enviador.atualizar(produto, PRODUTO_GID)

    assert not [q for q, _ in enviador.cliente.chamadas if "publication" in q.casefold()]
