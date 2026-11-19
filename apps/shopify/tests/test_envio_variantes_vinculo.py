"""Variante no update do produto para o Shopify: SKU primeiro, depois o id (vinculo).

Vinculo apontando para variante que nao existe mais na loja (recriada la, ou o produto
religado pelo SKU) derrubava o update inteiro com "variants.0.id: Product variant does
not exist": o preco alterado no hub nunca chegava. Variante sem vinculo mas que ja
existe na loja (mesmo SKU) ia para o productVariantsBulkCreate e duplicava/falhava.
A resposta do productUpdate traz as variantes da loja e o hub acha cada uma pelo SKU,
depois pelo vinculo, e so cria a que nao esta la.
"""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import (
    Produto,
    VarianteProduto,
)
from apps.shopify.tests.test_envio_produtos import PRODUTO_GID, _enviador, _simples
from apps.shopify.tests.test_envio_produtos_atualizar import BULK_CREATE, BULK_UPDATE, LOCAL


def _pv(numero):
    return f"gid://shopify/ProductVariant/{numero}"


def _update(*variantes, opcoes=("Title",)):
    return {"productUpdate": {"product": {
        "id": PRODUTO_GID, "media": {"nodes": []},
        "options": [{"name": nome} for nome in opcoes],
        "variants": {"nodes": [
            {"id": _pv(n), "sku": sku,
             "inventoryItem": {"id": f"gid://shopify/InventoryItem/{n}"}}
            for n, sku in variantes]},
    }, "userErrors": []}}


def _respostas(*variantes, **kw):
    return {"productVariantsBulkUpdate": BULK_UPDATE, "productVariantsBulkCreate": BULK_CREATE,
            "productUpdate": _update(*variantes, **kw), "location": LOCAL}


def _vincular(variante, numero):
    ExternalReference.objects.create(
        platform="shopify", entity_type="variantes", object_id=str(variante.pk),
        external_id=_pv(numero), external_parent_id=PRODUTO_GID)


def _chamada(enviador, raiz):
    return next(v for q, v in enviador.cliente.chamadas if raiz in q)


def _chamou(enviador, raiz):
    return any(raiz in q for q, _ in enviador.cliente.chamadas)


def _ids_no_lote(enviador):
    return sorted(v["id"] for v in _chamada(enviador, "productVariantsBulkUpdate")["variants"])


def _vinculos(variante):
    return list(ExternalReference.objects.filter(
        entity_type="variantes", object_id=str(variante.pk)).values_list("external_id",
                                                                         flat=True))


def _sofa(*skus):
    produto = Produto.objects.create(nome="Sofa", tipo=Produto.Tipo.VARIAVEL)
    return produto, [VarianteProduto.objects.create(
        produto=produto, titulo=sku, sku=sku, price=Decimal("10"), posicao=n)
        for n, sku in enumerate(skus)]


@pytest.mark.django_db
def test_vinculo_velho_e_trocado_pela_variante_da_loja_com_o_mesmo_sku(conta):
    produto, variante = _simples()
    _vincular(variante, 1)  # PV/1 nao existe mais na loja
    enviador = _enviador(conta, _respostas((5, "MESA-1")))

    enviador.atualizar(produto, PRODUTO_GID)

    [enviada] = _chamada(enviador, "productVariantsBulkUpdate")["variants"]
    assert enviada["id"] == _pv(5) and enviada["price"] == "80.00"
    assert not _chamou(enviador, "productVariantsBulkCreate")
    assert _vinculos(variante) == [_pv(5)]


@pytest.mark.django_db
def test_sku_vale_mais_que_o_vinculo_trocado(conta):
    """Vinculo de A aponta para a variante B da loja (e vice-versa): o SKU desfaz a troca."""
    produto, (bege, prata) = _sofa("SOFA-BG", "SOFA-PT")
    _vincular(bege, 2)
    _vincular(prata, 1)
    enviador = _enviador(conta, _respostas((1, "SOFA-BG"), (2, "SOFA-PT")))

    enviador.atualizar(produto, PRODUTO_GID)

    assert (_vinculos(bege), _vinculos(prata)) == ([_pv(1)], [_pv(2)])


@pytest.mark.django_db
def test_variante_sem_vinculo_que_ja_esta_na_loja_e_atualizada_e_nao_criada(conta):
    produto, (bege, prata) = _sofa("SOFA-BG", "SOFA-PT")
    _vincular(bege, 1)
    enviador = _enviador(conta, _respostas((1, "SOFA-BG"), (2, "SOFA-PT")))

    enviador.atualizar(produto, PRODUTO_GID)

    assert _ids_no_lote(enviador) == [_pv(1), _pv(2)]
    assert not _chamou(enviador, "productVariantsBulkCreate")
    assert _vinculos(prata) == [_pv(2)]


@pytest.mark.django_db
def test_sem_sku_igual_vale_o_vinculo(conta):
    produto, (bege,) = _sofa("SOFA-NOVO")
    _vincular(bege, 3)
    enviador = _enviador(conta, _respostas((3, "SOFA-ANTIGO"), (4, "OUTRA")))

    enviador.atualizar(produto, PRODUTO_GID)

    assert _ids_no_lote(enviador) == [_pv(3)]


@pytest.mark.django_db
def test_produto_de_uma_variante_usa_a_unica_variante_da_loja(conta):
    """Sem SKU igual e com vinculo velho, uma de cada lado e a mesma variante."""
    produto, variante = _simples()
    _vincular(variante, 1)
    enviador = _enviador(conta, _respostas((7, "OUTRO")))

    enviador.atualizar(produto, PRODUTO_GID)

    assert _ids_no_lote(enviador) == [_pv(7)]
    assert _vinculos(variante) == [_pv(7)]


@pytest.mark.django_db
def test_variante_realmente_nova_continua_sendo_criada(conta):
    produto, (bege, prata) = _sofa("SOFA-BG", "SOFA-PT")
    _vincular(bege, 1)
    enviador = _enviador(conta, _respostas((1, "SOFA-BG")))

    enviador.atualizar(produto, PRODUTO_GID)

    assert _ids_no_lote(enviador) == [_pv(1)]
    assert _chamou(enviador, "productVariantsBulkCreate")
    assert _vinculos(prata) == [_pv(2)]
