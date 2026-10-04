import logging
from decimal import Decimal

from apps.loja.models import Produto
from apps.loja.services.variantes import criar_produto

URL = "/wp-json/wc/v3/products"


def test_v3_consulta_produto_por_sku_e_exibe_os_filtros(api, caplog):
    """O ERP usa wc/v3; a consulta nao pode cair no 404 sem mostrar o filtro."""
    criar_produto("Caneca", sku="1490")

    with caplog.at_level(logging.INFO, logger="django.request"):
        resposta = api.get(f"{URL}/?sku=1490")

    assert resposta.status_code == 200
    assert [produto["sku"] for produto in resposta.json()] == ["1490"]
    assert "Woo v3 consultou produtos" in caplog.text
    assert "1490" in caplog.text


def test_v3_atualiza_produto_e_exibe_o_corpo_recebido(api, caplog):
    """A v3 altera somente os dois precos e o estoque permitidos pelo negocio."""
    produto = criar_produto("Caneca", sku="1490", price="10.00", inventory_quantity=2)

    with caplog.at_level(logging.INFO, logger="django.request"):
        resposta = api.put(
            f"{URL}/{produto.pk}",
            {
                "name": "Caneca grande",
                "catalog_visibility": "hidden",
                "regular_price": "29.90",
                "sale_price": "24.90",
                "stock_quantity": "25",
            },
            format="json",
        )

    assert resposta.status_code == 200
    assert resposta.json()["name"] == "Caneca"
    assert resposta.json()["catalog_visibility"] == "visible"
    assert resposta.json()["regular_price"] == "29.90"
    assert resposta.json()["sale_price"] == "24.90"
    assert resposta.json()["stock_quantity"] == 25
    produto.refresh_from_db()
    variante = produto.variantes.get(is_default=True)
    assert (variante.price, variante.sale_price) == (Decimal("29.90"), Decimal("24.90"))
    assert variante.inventory_quantity == 25
    assert "Woo v3 recebeu atualizacao do produto" in caplog.text
    assert "Caneca grande" in caplog.text


def test_v3_nao_cria_produto(api):
    """Produto ausente pertence a outra origem; o ERP nao pode cria-lo pela v3."""
    resposta = api.post(
        URL,
        {"name": "Produto indevido", "sku": "NOVO", "regular_price": "10.00"},
        format="json",
    )

    assert resposta.status_code == 404
    assert resposta.json()["code"] == "rest_no_route"
    assert not Produto.objects.filter(nome="Produto indevido").exists()


def test_v3_update_de_produto_inexistente_nao_cria_produto(api):
    """Um PUT com ID desconhecido deve terminar sem transformar update em criacao."""
    resposta = api.put(
        f"{URL}/999999",
        {"regular_price": "10.00", "sale_price": "9.00", "stock_quantity": 3},
        format="json",
    )

    assert resposta.status_code == 404
    assert not Produto.objects.exists()


def test_v3_nao_exclui_produto(api):
    """A integracao de estoque e preco nao pode remover um produto existente."""
    produto = criar_produto("Caneca", sku="1490")

    resposta = api.delete(f"{URL}/{produto.pk}?force=true")

    assert resposta.status_code == 404
    assert Produto.objects.filter(pk=produto.pk).exists()


def test_v3_lote_recusa_criacao_e_exclusao_de_produtos(api):
    """O endpoint de lote nao pode contornar a regra de somente atualizar produtos."""
    produto = criar_produto("Caneca", sku="1490")

    resposta = api.post(
        f"{URL}/batch",
        {"create": [{"name": "Novo"}], "delete": [produto.pk]},
        format="json",
    )

    assert resposta.status_code == 400
    assert Produto.objects.filter(pk=produto.pk).exists()
    assert not Produto.objects.filter(nome="Novo").exists()


def test_v3_nao_exibe_credenciais_passadas_na_consulta(api, caplog):
    """A observacao da consulta nunca pode imprimir a chave ou o segredo do ERP."""
    with caplog.at_level(logging.INFO, logger="django.request"):
        resposta = api.get(
            f"{URL}?sku=1490&consumer_key=ck_secreta&consumer_secret=cs_secreto"
        )

    assert resposta.status_code == 200
    assert "consumer_key" not in caplog.text
    assert "ck_secreta" not in caplog.text
    assert "consumer_secret" not in caplog.text
    assert "cs_secreto" not in caplog.text
