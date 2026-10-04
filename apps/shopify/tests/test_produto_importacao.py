"""Produto que ja existe: so a sincronizacao de importacao deixa o Shopify mandar.

Decisao do Matheus: webhook, produto faltante de pedido e eco de exportacao mantem
o que o hub tem (nome incluido); a importacao traz os dados completos da loja.
"""

from unittest.mock import patch

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Categoria, Produto
from apps.shopify import pedidos_produtos, recursos, sincronizar
from apps.shopify.contexto import usando_configuracao
from apps.shopify.tests.test_imagens_webhook import _configuracao
from apps.shopify.tests.test_produto_completo import GID, LojaFalsa, node
from apps.shopify.tests.test_sincronizar import _configuracao as _so_busca
from apps.shopify.webhooks import processar_webhook


def _hub_ja_tem_o_produto():
    recursos.produto(node())
    produto = Produto.objects.get(slug="poltrona-azul")
    produto.nome = "Nome do hub"
    produto.descricao = "<p>Do hub</p>"
    produto.fornecedor = "Hub SA"
    produto.seo_titulo = "SEO do hub"
    produto.save()
    produto.categorias.add(Categoria.objects.create(nome="So no hub", slug="so-no-hub"))
    return produto


def _importar(dados):
    class Cliente:
        def __init__(self, _configuracao):
            pass

        def contar(self, _recurso):
            return None

        def listar(self, _recurso):
            return iter([dados])

    with patch.object(sincronizar, "ShopifyClient", Cliente), \
            patch.dict(sincronizar.CONVERSORES, {}, clear=True):
        sincronizar.sincronizar_loja(_so_busca(("produtos", "get")), lambda *_: None, ["produtos"])


@pytest.mark.django_db
def test_importacao_sobrescreve_o_produto_que_ja_existe_no_hub(conta):
    """Sem isso a importacao deixava nome, texto e SEO velhos do hub para sempre."""
    produto = _hub_ja_tem_o_produto()
    variantes = node()["variants"]
    variantes["nodes"][0].update(title="Azul", sku="POL-2")

    _importar(node(title="Nome da loja", descriptionHtml="<p>Da loja</p>", vendor="FDC 2",
                   seo={"title": "SEO da loja", "description": ""}, tags=["quarto"],
                   status="DRAFT", variants=variantes))

    produto.refresh_from_db()
    assert (produto.nome, produto.descricao, produto.fornecedor) == (
        "Nome da loja", "<p>Da loja</p>", "FDC 2")
    assert (produto.seo_titulo, produto.seo_descricao) == ("SEO da loja", "")
    assert produto.status == Produto.Status.RASCUNHO
    assert list(produto.tags.values_list("nome", flat=True)) == ["quarto"]
    assert list(produto.categorias.all()) == [], "colecoes da loja valem, sem as do hub"
    variante = produto.variante_padrao
    assert (variante.titulo, variante.sku) == ("Azul", "POL-2")


@pytest.mark.django_db
def test_webhook_de_produto_mantem_o_nome_do_hub(conta):
    """Atualizacao por webhook nao pode trocar o nome que o operador escolheu."""
    produto = _hub_ja_tem_o_produto()
    configuracao = _configuracao(conta)
    loja = LojaFalsa(node(title="Nome da loja", vendor="FDC 2", tags=["quarto"]))
    corpo = {"id": 700, "admin_graphql_api_id": GID, "title": "REST", "variants": []}

    with patch("apps.shopify.produtos_busca.ShopifyClient", loja), \
            usando_configuracao(configuracao):
        processar_webhook(configuracao, "produtos", "create", corpo, lambda *_: None)

    produto.refresh_from_db()
    assert produto.nome == "Nome do hub"
    assert list(produto.categorias.values_list("slug", flat=True)) == ["so-no-hub"]


@pytest.mark.django_db
def test_produto_faltante_de_pedido_mantem_o_nome_do_hub(conta):
    """Item de pedido cujo produto ja existe nao pode sobrescrever o cadastro do hub."""
    produto = _hub_ja_tem_o_produto()
    ExternalReference.objects.filter(entity_type="produtos").update(object_id=str(produto.pk))
    configuracao = _configuracao(conta)

    class Cliente:
        def __init__(self, _configuracao):
            pass

        def graphql(self, *_args):
            return {"product": node(title="Nome da loja")}

    # Sem variante local o produto e buscado de novo: apaga a variante e o vinculo dela.
    produto.variantes.all().delete()
    with patch.object(pedidos_produtos, "ShopifyClient", Cliente), \
            usando_configuracao(configuracao):
        pedidos_produtos.garantir_produto(
            {"id": 1, "product_id": 700, "variant_id": 701, "sku": "POL-1"})

    produto.refresh_from_db()
    assert produto.nome == "Nome do hub"
