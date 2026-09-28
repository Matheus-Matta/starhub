from decimal import Decimal

from apps.core.models import Origin
from apps.loja.models import Categoria, MidiaProduto, Produto
from apps.loja.services.variantes import criar_produto
from apps.woo_api.tests.conftest import json_com_numeros

URL = "/wp-json/wc/v1/products"


def test_preco_enviado_como_numero_chega_exato(api):
    """O parser padrao leria 19.9 como float; o centavo tem que chegar exato."""
    resposta = json_com_numeros(
        api, "post", URL, '{"name": "Caneca", "regular_price": 19.9, "sku": "CAN-1"}'
    )
    assert resposta.status_code == 201, resposta.json()
    assert resposta.json()["regular_price"] == "19.90"
    assert Produto.objects.get().preco_regular == Decimal("19.90")


def test_resposta_tem_os_campos_do_woocommerce(api):
    corpo = api.post(URL, {"name": "Caneca"}, format="json").json()
    for campo in (
        "id",
        "slug",
        "permalink",
        "date_created",
        "date_created_gmt",
        "price",
        "regular_price",
        "sale_price",
        "stock_status",
        "manage_stock",
        "categories",
        "images",
        "meta_data",
        "dimensions",
        "attributes",
    ):
        assert campo in corpo
    assert corpo["slug"] == "caneca"


def test_sku_repetido_devolve_erro_do_woo_com_id_existente(api):
    primeiro = api.post(URL, {"name": "A", "sku": "X1"}, format="json").json()
    resposta = api.post(URL, {"name": "B", "sku": "X1"}, format="json")
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "product_invalid_sku"
    assert resposta.json()["data"]["resource_id"] == primeiro["id"]


def test_estoque_gerenciado_define_a_situacao(api):
    corpo = api.post(
        URL, {"name": "A", "manage_stock": True, "stock_quantity": 0}, format="json"
    ).json()
    assert corpo["stock_status"] == "outofstock"
    alterado = api.put(f"{URL}/{corpo['id']}", {"stock_quantity": 7}, format="json").json()
    assert alterado["stock_status"] == "instock"
    assert alterado["stock_quantity"] == 7
    assert alterado["name"] == "A"  # PUT parcial nao apaga o resto


def test_promocao_define_price_e_on_sale(api):
    corpo = api.post(
        URL, {"name": "A", "regular_price": "100", "sale_price": "80"}, format="json"
    ).json()
    assert (corpo["price"], corpo["on_sale"]) == ("80.00", True)


def test_categorias_por_id(api):
    categoria = Categoria.objects.create(nome="Copa", slug="copa")
    corpo = api.post(
        URL, {"name": "A", "categories": [{"id": categoria.pk}, {"id": 999}]}, format="json"
    ).json()
    assert corpo["categories"] == [{"id": categoria.pk, "name": "Copa", "slug": "copa"}]


def test_listagem_pagina_com_cabecalhos_do_wordpress(api):
    for n in range(3):
        criar_produto(f"P{n}", sku=f"S{n}")
    resposta = api.get(f"{URL}?per_page=2&page=1")
    assert len(resposta.json()) == 2
    assert resposta["X-WP-Total"] == "3"
    assert resposta["X-WP-TotalPages"] == "2"
    assert 'rel="next"' in resposta["Link"]
    assert api.get(f"{URL}?per_page=2&page=2").json()[0]["sku"] == "S0"


def test_per_page_acima_de_100_e_parametro_invalido(api):
    resposta = api.get(f"{URL}?per_page=101")
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "rest_invalid_param"


def test_filtro_por_sku(api):
    criar_produto("A", sku="AAA")
    criar_produto("B", sku="BBB")
    assert [p["sku"] for p in api.get(f"{URL}?sku=BBB").json()] == ["BBB"]


def test_excluir_sem_force_vai_para_lixeira_e_some_da_lista(api):
    produto = Produto.objects.create(nome="A")
    assert api.delete(f"{URL}/{produto.pk}").json()["status"] == "trash"
    assert api.get(URL).json() == []
    assert api.delete(f"{URL}/{produto.pk}").status_code == 410
    assert api.delete(f"{URL}/{produto.pk}?force=true").status_code == 200
    assert not Produto.objects.exists()


def test_id_inexistente_devolve_404_no_formato_woo(api):
    resposta = api.get(f"{URL}/999")
    assert resposta.status_code == 404
    assert resposta.json()["code"] == "woocommerce_rest_product_invalid_id"


def test_lote_cria_altera_exclui_e_isola_o_item_com_erro(api):
    existente = criar_produto("Velho", sku="V1")
    apagar = Produto.objects.create(nome="Apagar")
    resposta = api.post(
        f"{URL}/batch",
        {
            "create": [{"name": "Novo", "sku": "N1"}, {"name": "Repetido", "sku": "V1"}],
            "update": [{"id": existente.pk, "regular_price": "5.50"}],
            "delete": [apagar.pk],
        },
        format="json",
    ).json()
    assert resposta["create"][0]["sku"] == "N1"
    assert resposta["create"][1]["error"]["code"] == "product_invalid_sku"
    assert resposta["update"][0]["regular_price"] == "5.50"
    assert resposta["delete"][0]["id"] == apagar.pk
    assert Produto.objects.filter(variantes__sku="N1").exists()


def test_lote_acima_de_100_e_recusado(api):
    resposta = api.post(f"{URL}/batch", {"delete": list(range(1, 102))}, format="json")
    assert resposta.status_code == 413


def test_api_woo_devolve_url_completa_da_imagem_enviada(api):
    produto = Produto.objects.create(nome="A")
    MidiaProduto.objects.create(produto=produto, url="/media/produtos/x.png")
    corpo = api.get(f"/wp-json/wc/v1/products/{produto.pk}").json()
    assert corpo["images"][0]["src"] == "http://testserver/media/produtos/x.png"


def test_produto_com_nome_repetido_ganha_slug_com_sufixo(api):
    """O slug e unico por conta: antes o segundo "Caneca" estourava o indice e o
    ERP recebia product_invalid_sku, um erro que nao tinha nada a ver."""
    api.post(URL, {"name": "Caneca"}, format="json")
    resposta = api.post(URL, {"name": "Caneca"}, format="json")
    assert resposta.status_code == 201
    assert resposta.json()["slug"] == "caneca-2"


def test_produto_criado_pela_api_tem_origem_api_e_variante_padrao(api):
    corpo = api.post(URL, {"name": "A", "sku": "A1", "regular_price": "9.90"}, format="json").json()
    produto = Produto.objects.get(pk=corpo["id"])
    assert produto.origin == Origin.API
    [variante] = produto.variantes.all()
    assert (variante.is_default, variante.sku, str(variante.price)) == (True, "A1", "9.90")


def test_imagens_da_api_vao_para_a_galeria_da_variante_padrao(api):
    corpo = api.post(URL, {"name": "A", "images": [
        {"src": "https://cdn.test/1.jpg"}, {"src": "https://cdn.test/2.jpg"},
    ]}, format="json").json()
    produto = Produto.objects.get(pk=corpo["id"])
    assert produto.variante_padrao.midias.count() == 2
    primeira, segunda = corpo["images"]
    # O ERP reordena devolvendo os ids: as mesmas imagens, na ordem nova.
    alterado = api.put(f"{URL}/{corpo['id']}", {"images": [segunda, primeira]}, format="json")
    assert [i["id"] for i in alterado.json()["images"]] == [segunda["id"], primeira["id"]]
