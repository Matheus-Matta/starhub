import logging

from apps.loja.models import Categoria

URL = "/wp-json/wc/v3/products/categories"


def test_v3_cria_categoria_realmente(api):
    """Categoria e item secundario e precisa ser criada quando o ERP nao a encontra."""
    resposta = api.post(
        URL,
        {"name": "Sala de jantar", "slug": "sala-de-jantar"},
        format="json",
    )

    assert resposta.status_code == 201
    assert Categoria.objects.filter(nome="Sala de jantar", slug="sala-de-jantar").exists()


def test_v3_consulta_categoria_pelo_slug_exato_e_exibe_o_filtro(api, caplog):
    """A busca de categoria feita pelo ERP nao pode cair no 404 nem devolver todas."""
    Categoria.objects.create(nome="Cozinha", slug="cozinha")
    procurada = Categoria.objects.create(nome="Sala de estar", slug="sala-de-estar")

    with caplog.at_level(logging.INFO, logger="django.request"):
        resposta = api.get(f"{URL}/?slug=sala-de-estar")

    assert resposta.status_code == 200
    assert [categoria["id"] for categoria in resposta.json()] == [procurada.pk]
    assert "Woo v3 consultou categorias" in caplog.text
    assert "sala-de-estar" in caplog.text


def test_v3_atualiza_categoria_e_exibe_o_corpo_recebido(api, caplog):
    """A atualizacao de categoria v3 precisa funcionar e ficar visivel no terminal."""
    categoria = Categoria.objects.create(nome="Quarto", slug="quarto")

    with caplog.at_level(logging.INFO, logger="django.request"):
        resposta = api.put(
            f"{URL}/{categoria.pk}",
            {"name": "Quarto infantil", "description": "Moveis infantis"},
            format="json",
        )

    assert resposta.status_code == 200
    assert resposta.json()["name"] == "Quarto infantil"
    assert "Woo v3 recebeu atualizacao da categoria" in caplog.text
    assert "Moveis infantis" in caplog.text
