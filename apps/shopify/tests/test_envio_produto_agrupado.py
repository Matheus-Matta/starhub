"""Produto simples na loja que virou variavel no hub (agrupamento, loja/services/agrupar.py).

Na loja o produto tem so a opcao padrao "Title". O update mandava as variantes novas
com a opcao "Tamanho", que a loja nao tinha: ficavam de fora com aviso e o produto da
loja continuava simples. Agora o productOptionsCreate troca o "Title" pela opcao do
hub antes (a variante que ja existe recebe o valor dela) e as outras sao criadas.
"""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Produto
from apps.loja.services.agrupar import agrupar
from apps.shopify.tests.test_envio_produtos import PRODUTO_GID, _enviador
from apps.shopify.tests.test_envio_produtos_atualizar import BULK_CREATE, BULK_UPDATE, LOCAL
from apps.shopify.tests.test_envio_variantes_vinculo import (
    _chamada,
    _chamou,
    _update,
    _vincular,
)

OPCOES_CRIADAS = {"productOptionsCreate": {
    "product": {"id": PRODUTO_GID, "options": [{"name": "Tamanho"}]}, "userErrors": []}}


def _camiseta_agrupada():
    simples = []
    for nome, sku in (("Camiseta P", "CAM-P"), ("Camiseta M", "CAM-M")):
        produto = Produto.objects.create(nome=nome)
        variante = produto.variante_padrao
        variante.sku, variante.price = sku, Decimal("49.90")
        variante.save()
        simples.append(produto)
    p, m = simples
    _vincular(p.variante_padrao, 1)  # a P ja estava na loja, simples
    return agrupar(p.pk, [p.pk, m.pk], "Camiseta", "Tamanho", {p.pk: "P", m.pk: "M"})


def _enviador_da_loja(conta, *opcoes):
    return _enviador(conta, {
        "productOptionsCreate": OPCOES_CRIADAS, "productUpdate": _update(
            (1, "CAM-P"), opcoes=opcoes or ("Title",)),
        "productVariantsBulkUpdate": BULK_UPDATE, "productVariantsBulkCreate": BULK_CREATE,
        "location": LOCAL})


@pytest.mark.django_db
def test_produto_simples_da_loja_ganha_a_opcao_e_as_variantes_novas(conta):
    pai = _camiseta_agrupada()
    enviador = _enviador_da_loja(conta)

    enviador.atualizar(pai, PRODUTO_GID)

    opcoes = _chamada(enviador, "productOptionsCreate")
    assert opcoes["productId"] == PRODUTO_GID
    assert opcoes["variantStrategy"] == "LEAVE_AS_IS"
    # So o valor da variante que ja existe: opcao com valor sem variante e recusada.
    assert opcoes["options"] == [{"name": "Tamanho", "position": 1, "values": [{"name": "P"}]}]
    [p] = _chamada(enviador, "productVariantsBulkUpdate")["variants"]
    assert p["optionValues"] == [{"optionName": "Tamanho", "name": "P"}]
    [m] = _chamada(enviador, "productVariantsBulkCreate")["variants"]
    assert m["inventoryItem"]["sku"] == "CAM-M"
    assert m["optionValues"] == [{"optionName": "Tamanho", "name": "M"}]
    assert ExternalReference.objects.filter(entity_type="variantes").count() == 2


@pytest.mark.django_db
def test_produto_que_ja_tem_opcao_na_loja_nao_recria_opcao(conta):
    """productOptionsCreate com opcao repetida da OPTION_ALREADY_EXISTS e derruba o envio."""
    pai = _camiseta_agrupada()
    enviador = _enviador_da_loja(conta, "Tamanho")

    enviador.atualizar(pai, PRODUTO_GID)

    assert not _chamou(enviador, "productOptionsCreate")
    assert _chamou(enviador, "productVariantsBulkCreate")
