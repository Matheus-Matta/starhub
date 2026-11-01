"""ERP que cria produto (id 0) com SKU: o hub acha a variante pelo SKU e atualiza."""

from decimal import Decimal

import pytest

from apps.loja.models import Produto, VarianteProduto
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db
URL = "/wp-json/wc/v3/products"


@pytest.fixture
def escrivaninha(conta):
    """Produto com duas variantes: o SKU decide qual recebe preco e estoque."""
    produto = criar_produto("ESCRIVANINHA", sku="7657", price="159.99", inventory_quantity=49)
    VarianteProduto.objects.create(produto=produto, titulo="Cedro", sku="7656",
                                   price=Decimal("159.99"), inventory_quantity=47)
    return produto


def _variantes(produto):
    return dict(produto.variantes.values_list("sku", "inventory_quantity"))


def test_criacao_com_sku_existente_atualiza_a_variante_e_devolve_o_id(api, escrivaninha):
    """O ERP manda id 0 quando nao sabe o id: sem isto recebia 404 e nada atualizava."""
    resposta = api.post(URL, {"id": "0", "sku": "7656", "name": "OUTRO NOME",
                              "catalog_visibility": "hidden", "regular_price": "499.99",
                              "sale_price": "319.99", "stock_quantity": "8"}, format="json")

    assert resposta.status_code == 201
    assert resposta.json()["id"] == escrivaninha.pk
    variante = VarianteProduto.objects.get(sku="7656")
    assert (variante.price, variante.sale_price) == (Decimal("499.99"), Decimal("319.99"))
    assert _variantes(escrivaninha) == {"7657": 49, "7656": 8}
    assert Produto.objects.count() == 1
    assert Produto.objects.get().nome == "ESCRIVANINHA", "nome e o do Shopify, nao o do ERP"


def test_sku_que_o_hub_nao_tem_vira_produto_simples_inativo(api, escrivaninha):
    """O ERP tem produto que o Shopify ainda nao tem: recusar deixava o ERP em laco."""
    resposta = api.post(URL, {"id": "0", "sku": "2065", "name": "COMODA DUBAI",
                              "catalog_visibility": "visible", "regular_price": "599.99",
                              "sale_price": "", "stock_quantity": "2"}, format="json")

    assert resposta.status_code == 201
    novo = Produto.objects.get(pk=resposta.json()["id"])
    assert (novo.nome, novo.tipo, novo.status, novo.active) == (
        "COMODA DUBAI", "simple", "draft", False)
    variante = novo.variantes.get()
    assert (variante.sku, variante.price, variante.sale_price, variante.inventory_quantity) == (
        "2065", Decimal("599.99"), None, 2)

    # O proximo envio do ERP (id 0 de novo, ou o id devolvido) atualiza o mesmo produto.
    api.post(URL, {"id": "0", "sku": "2065", "stock_quantity": "9"}, format="json")
    api.put(f"{URL}/{novo.pk}", {"regular_price": "549.99"}, format="json")
    variante.refresh_from_db()
    assert (variante.inventory_quantity, variante.price) == (9, Decimal("549.99"))
    assert Produto.objects.count() == 2


def test_criacao_sem_sku_diz_ao_erp_o_que_mandar(api, escrivaninha):
    resposta = api.post(URL, {"id": "0", "name": "ESCRIVANINHA", "stock_quantity": "3"},
                        format="json")

    assert resposta.status_code == 404
    assert "sku" in resposta.json()["message"]
    assert Produto.objects.count() == 1
    assert _variantes(escrivaninha) == {"7657": 49, "7656": 47}


def test_atualizacao_com_sku_de_outra_variante_do_produto_mexe_nela(api, escrivaninha):
    """Com o id do pai, o PUT so alcancava a variante padrao."""
    resposta = api.put(f"{URL}/{escrivaninha.pk}", {"sku": "7656", "stock_quantity": "5"},
                       format="json")

    assert resposta.status_code == 200
    assert _variantes(escrivaninha) == {"7657": 49, "7656": 5}


def test_atualizacao_com_sku_desconhecido_segue_na_variante_padrao(api, escrivaninha):
    """O ERP pode mandar o codigo dele no sku: o PUT que ja funcionava nao pode quebrar."""
    outro = criar_produto("Caneca", sku="1490", inventory_quantity=1)

    for sku in ("CODIGO-DO-ERP", "1490"):
        resposta = api.put(f"{URL}/{escrivaninha.pk}", {"sku": sku, "stock_quantity": "7"},
                           format="json")
        assert resposta.status_code == 200
    assert _variantes(escrivaninha) == {"7657": 7, "7656": 47}
    assert _variantes(outro) == {"1490": 1}
