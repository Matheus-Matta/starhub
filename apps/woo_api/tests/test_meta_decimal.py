"""meta_data com numero decimal (Decimal do parser) deve serializar sem erro 500."""

from apps.woo_api.tests.conftest import json_com_numeros

URL_PRODUTOS = "/wp-json/wc/v1/products"
URL_PEDIDOS = "/wp-json/wc/v1/orders"


def test_produto_com_meta_data_decimal_retorna_201(api):
    """Produto criado com meta_data contendo numero decimal (19.9) deve retornar numero.

    O JSONDecimalParser transforma 19.9 em Decimal. meta_data e dado opaco do ERP
    (nao dinheiro do hub), e o WooCommerce devolve numero como numero. Guardamos
    Decimal inteiro como int, Decimal com casas como float.
    """
    corpo = json_com_numeros(
        api, "post", URL_PRODUTOS,
        '{"name": "Produto", "sku": "PESO-1", '
        '"meta_data": [{"key": "peso_extra", "value": 19.9}, {"key": "qtd", "value": 3}]}'
    )
    assert corpo.status_code == 201, corpo.json()
    dados = corpo.json()
    meta = dados["meta_data"]
    assert meta[0]["key"] == "peso_extra" and isinstance(meta[0]["value"], float)
    assert meta[0]["value"] == 19.9
    assert meta[1]["key"] == "qtd" and isinstance(meta[1]["value"], int)
    assert meta[1]["value"] == 3


def test_pedido_com_meta_data_decimal_retorna_200(api, db):
    """Pedido com meta_data contendo numero decimal deve retornar numero.

    meta_data opaca: valores numericos sao devolvidos como numeros, igual ao Woo.
    """
    from apps.loja.models import Pedido

    pedido = Pedido.objects.create(status="processing")
    corpo = json_com_numeros(
        api, "put", f"{URL_PEDIDOS}/{pedido.pk}",
        '{"meta_data": [{"key": "taxa_extra", "value": 5.5}]}'
    )
    assert corpo.status_code == 200, corpo.json()
    dados = corpo.json()
    meta = dados["meta_data"]
    assert meta[0]["key"] == "taxa_extra" and isinstance(meta[0]["value"], float)
    assert meta[0]["value"] == 5.5
