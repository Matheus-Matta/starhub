"""SEO do produto no Shopify: vai so o que o hub tem preenchido.

Mandar `seo` com texto vazio apagaria o SEO cadastrado direto na loja so porque o
hub ainda nao tem o campo preenchido.
"""

import pytest

from apps.shopify.tests.test_envio_produtos import _enviador, _resposta_set, _simples
from apps.shopify.tests.test_envio_produtos_atualizar import _chamada, _respostas, _vincular


def _atualizar(conta, produto):
    enviador = _enviador(conta, _respostas())
    enviador.atualizar(produto, "900")
    return _chamada(enviador, "productUpdate")["product"]


@pytest.mark.django_db
def test_update_manda_seo_quando_o_hub_tem(conta):
    produto, variante = _simples()
    _vincular(variante, 1)
    produto.seo_titulo, produto.seo_descricao = "Mesa de jantar", "Mesa boa e barata"
    produto.save()

    entrada = _atualizar(conta, produto)

    assert entrada["seo"] == {"title": "Mesa de jantar", "description": "Mesa boa e barata"}


@pytest.mark.django_db
def test_seo_vazio_no_hub_nao_vai_para_a_loja(conta):
    produto, variante = _simples()
    _vincular(variante, 1)

    entrada = _atualizar(conta, produto)

    assert "seo" not in entrada


@pytest.mark.django_db
def test_so_o_titulo_preenchido_manda_so_o_titulo(conta):
    produto, variante = _simples()
    _vincular(variante, 1)
    produto.seo_titulo = "Mesa de jantar"
    produto.save()

    entrada = _atualizar(conta, produto)

    assert entrada["seo"] == {"title": "Mesa de jantar"}


@pytest.mark.django_db
def test_criacao_tambem_manda_o_seo(conta):
    produto, _variante = _simples()
    produto.seo_descricao = "Mesa boa e barata"
    produto.save()
    enviador = _enviador(conta, {"productSet": _resposta_set(1), "location": {
        "location": {"id": "gid://shopify/Location/1"}}})

    enviador.criar(produto)

    entrada = _chamada(enviador, "productSet")["input"]
    assert entrada["seo"] == {"description": "Mesa boa e barata"}
