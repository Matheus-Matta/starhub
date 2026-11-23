"""Id de produto simples que foi agrupado num variavel (loja/services/agrupar.py).

O ERP guardou o id de cada simples (Camiseta P = 12, M = 13) e continua mandando
PUT /products/13 com preco e estoque. Depois do agrupamento o 13 nao existe mais: sem
o desvio, o ERP recebia 404 e o estoque da M parava de atualizar.
"""

from decimal import Decimal

import pytest

from apps.loja.models import Produto, VarianteProduto
from apps.loja.services.agrupar import agrupar
from apps.woo_api.recursos.produtos_variacao import BASE_VARIACAO

pytestmark = pytest.mark.django_db
V3 = "/wp-json/wc/v3/products"
V1 = "/wp-json/wc/v1/products"


@pytest.fixture
def agrupados():
    simples = []
    for nome, sku in (("Camiseta P", "CAM-P"), ("Camiseta M", "CAM-M")):
        produto = Produto.objects.create(nome=nome)
        variante = produto.variante_padrao
        variante.sku, variante.price, variante.inventory_quantity = sku, Decimal("49.90"), 1
        variante.save()
        simples.append(produto)
    p, m = simples
    agrupar(p.pk, [p.pk, m.pk], "Camiseta", "Tamanho", {p.pk: "P", m.pk: "M"})
    return p, m.pk, VarianteProduto.objects.get(sku="CAM-M")


def test_put_no_id_do_simples_agrupado_grava_na_variacao_que_veio_dele(api, agrupados):
    pai, id_antigo, variante = agrupados

    resposta = api.put(f"{V3}/{id_antigo}", {"regular_price": "59.90", "stock_quantity": 8},
                       format="json")

    assert resposta.status_code == 200, resposta.content
    variante.refresh_from_db()
    assert (variante.price, variante.inventory_quantity) == (Decimal("59.90"), 8)
    assert resposta.json()["id"] == BASE_VARIACAO + variante.pk
    assert resposta.json()["parent_id"] == pai.pk
    # A variacao do pai (a P) nao recebe o preco que era da M.
    assert pai.variante_padrao.price == Decimal("49.90")


def test_get_no_id_antigo_devolve_a_variacao(api, agrupados):
    pai, id_antigo, variante = agrupados

    dados = api.get(f"{V3}/{id_antigo}").json()

    assert (dados["type"], dados["sku"], dados["parent_id"]) == ("variation", "CAM-M", pai.pk)


def test_id_antigo_vale_tambem_na_v1(api, agrupados):
    _pai, id_antigo, variante = agrupados

    resposta = api.put(f"{V1}/{id_antigo}", {"stock_quantity": 3}, format="json")

    assert resposta.status_code == 200, resposta.content
    variante.refresh_from_db()
    assert variante.inventory_quantity == 3


def test_id_que_nunca_existiu_continua_404(api, agrupados):
    resposta = api.put(f"{V3}/999999", {"stock_quantity": 3}, format="json")

    assert resposta.status_code == 404
    assert resposta.json()["code"] == "woocommerce_rest_product_invalid_id"
