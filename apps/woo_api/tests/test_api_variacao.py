"""Variacao de produto variavel pela API Woo: o id devolvido leva a variacao, nao a padrao.

O ERP faz POST products {"id": "0", "sku": ...}, guarda o "id" da resposta e depois
faz PUT products/<id> so com preco e estoque. Com o id do pai, o PUT caia na variante
padrao: a variacao pedida nunca mudava e a padrao ficava com o preco dela.
"""

from decimal import Decimal

import pytest

from apps.loja.models import Produto, VarianteProduto
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db
URL = "/wp-json/wc/v3/products"


@pytest.fixture
def camiseta(conta):
    produto = criar_produto("Camiseta", sku="CAM-P", price=Decimal("50.00"),
                            inventory_quantity=5, manage_inventory=True)
    produto.tipo = Produto.Tipo.VARIAVEL
    produto.save()
    VarianteProduto.objects.create(produto=produto, titulo="M", sku="CAM-M",
                                   price=Decimal("60.00"), inventory_quantity=3,
                                   manage_inventory=True, posicao=1)
    return produto


def _variantes():
    return {v.sku: (v.price, v.sale_price, v.inventory_quantity)
            for v in VarianteProduto.objects.all()}


def test_id_devolvido_pelo_sku_da_variacao_atualiza_a_variacao(api, camiseta):
    criada = api.post(URL, {"id": "0", "sku": "CAM-M", "stock_quantity": "9"}, format="json")
    id_variacao = criada.json()["id"]

    assert criada.status_code == 201 and id_variacao != camiseta.pk
    assert criada.json()["sku"] == "CAM-M" and criada.json()["parent_id"] == camiseta.pk

    resposta = api.put(f"{URL}/{id_variacao}", {"regular_price": "70.00", "sale_price": "65.00",
                                                "stock_quantity": "4"}, format="json")

    assert resposta.status_code == 200 and resposta.json()["id"] == id_variacao
    assert _variantes() == {"CAM-P": (Decimal("50.00"), None, 5),
                            "CAM-M": (Decimal("70.00"), Decimal("65.00"), 4)}


def test_sku_da_variante_padrao_continua_devolvendo_o_id_do_produto(api, camiseta):
    """Produto simples e a 1a variacao: o id que o ERP ja guardou nao muda."""
    resposta = api.post(URL, {"id": "0", "sku": "CAM-P", "stock_quantity": "8"}, format="json")
    assert resposta.json()["id"] == camiseta.pk
    assert _variantes()["CAM-P"][2] == 8


def test_put_no_pai_com_sku_da_variacao_devolve_o_id_da_variacao(api, camiseta):
    """O ERP que ja guardou o id do pai aprende o id certo na primeira resposta."""
    resposta = api.put(f"{URL}/{camiseta.pk}", {"sku": "CAM-M", "stock_quantity": "1"},
                       format="json")
    assert resposta.json()["sku"] == "CAM-M" and resposta.json()["id"] != camiseta.pk
    assert _variantes()["CAM-M"][2] == 1 and _variantes()["CAM-P"][2] == 5


@pytest.mark.parametrize("versao", ["v1", "v3"])
def test_consulta_pelo_sku_da_variacao_devolve_a_variacao(api, camiseta, versao):
    """Como no Woo: ?sku= acha a variacao, com o sku, preco e estoque dela."""
    lista = api.get(f"/wp-json/wc/{versao}/products", {"sku": "CAM-M"}).json()

    assert [(p["sku"], p["regular_price"], p["stock_quantity"], p["type"]) for p in lista] == [
        ("CAM-M", "60.00", 3, "variation")]
    detalhe = api.get(f"/wp-json/wc/{versao}/products/{lista[0]['id']}").json()
    assert detalhe["sku"] == "CAM-M" and detalhe["parent_id"] == camiseta.pk


def test_lote_com_o_id_da_variacao_atualiza_a_variacao(api, camiseta):
    id_variacao = api.get(URL, {"sku": "CAM-M"}).json()[0]["id"]

    resposta = api.post(f"{URL}/batch", {"update": [{"id": id_variacao, "stock_quantity": 2}]},
                        format="json")

    assert resposta.json()["update"][0]["sku"] == "CAM-M"
    assert _variantes()["CAM-M"][2] == 2 and _variantes()["CAM-P"][2] == 5


def test_v1_altera_so_a_variacao_e_nao_exclui_o_produto_pelo_id_dela(api, camiseta):
    id_variacao = api.get(URL, {"sku": "CAM-M"}).json()[0]["id"]
    url = f"/wp-json/wc/v1/products/{id_variacao}"

    alterada = api.put(url, {"name": "Nao muda o pai", "regular_price": "61.00"}, format="json")
    excluida = api.delete(url, {"force": True})

    assert alterada.status_code == 200 and _variantes()["CAM-M"][0] == Decimal("61.00")
    assert Produto.objects.get().nome == "Camiseta"
    assert excluida.status_code == 400
    assert Produto.objects.get().status != Produto.Status.LIXEIRA
    assert VarianteProduto.objects.count() == 2


def _rota(camiseta, id_):
    return f"{URL}/{camiseta.pk}/variations/{id_}"


def test_rota_de_variacao_do_woo_altera_a_variacao(api, camiseta):
    """O ERP manda PUT products/<pai>/variations/<id>: sem a rota voltava 404 em HTML."""
    id_variacao = api.post(URL, {"id": "0", "sku": "CAM-M"}, format="json").json()["id"]
    corpo = {"id": str(id_variacao), "catalog_visibility": "visible", "regular_price": "129.99",
             "sale_price": "", "stock_quantity": "0", "name": "CAMISETA - M"}

    resposta = api.put(_rota(camiseta, id_variacao), corpo, format="json")

    assert resposta.status_code == 200
    assert resposta.json()["id"] == id_variacao and resposta.json()["sku"] == "CAM-M"
    assert _variantes() == {"CAM-P": (Decimal("50.00"), None, 5),
                            "CAM-M": (Decimal("129.99"), None, 0)}
    assert Produto.objects.get().nome == "Camiseta"


def test_rota_de_variacao_aceita_o_id_da_variante_e_o_do_pai(api, camiseta):
    m = VarianteProduto.objects.get(sku="CAM-M")
    assert api.put(_rota(camiseta, m.pk), {"stock_quantity": 1}, format="json").json()["sku"] \
        == "CAM-M"
    assert api.put(_rota(camiseta, camiseta.pk), {"stock_quantity": 2},
                   format="json").json()["sku"] == "CAM-P"
    assert _variantes()["CAM-M"][2] == 1 and _variantes()["CAM-P"][2] == 2


def test_variacao_de_outro_produto_da_404_no_formato_do_woo(api, camiseta):
    outro = criar_produto("Outro", sku="OUT-1")
    m = VarianteProduto.objects.get(sku="CAM-M")

    resposta = api.put(f"{URL}/{outro.pk}/variations/{1_000_000_000 + m.pk}",
                       {"stock_quantity": 1},
                       format="json")

    assert resposta.status_code == 404
    assert resposta.json()["code"] == "woocommerce_rest_product_variation_invalid_id"
    assert _variantes()["CAM-M"][2] == 3


def test_lista_e_lote_de_variacoes(api, camiseta):
    lista = api.get(f"{URL}/{camiseta.pk}/variations").json()
    assert [v["sku"] for v in lista] == ["CAM-P", "CAM-M"]

    m = VarianteProduto.objects.get(sku="CAM-M")
    lote = api.post(f"{URL}/{camiseta.pk}/variations/batch",
                    {"update": [{"id": m.pk, "stock_quantity": 7}]}, format="json")

    assert lote.json()["update"][0]["sku"] == "CAM-M" and _variantes()["CAM-M"][2] == 7
