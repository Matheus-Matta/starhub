"""Produto do Shopify importado inteiro: SEO, descricao, tags, colecoes, variantes.

Antes o webhook confiava no corpo REST (que nao traz SEO) e a sincronizacao de um
produto que ja existia no hub so trazia as imagens: SEO, tags e colecoes ficavam
desatualizados para sempre.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Categoria, Produto
from apps.shopify import recursos
from apps.shopify.contexto import usando_configuracao
from apps.shopify.tests.test_imagens_webhook import _configuracao
from apps.shopify.webhooks import processar_webhook

GID = "gid://shopify/Product/700"


class ErroDeRede(RuntimeError):
    pass


def node(**extra):
    base = {
        "id": GID, "title": "Poltrona", "handle": "poltrona-azul",
        "descriptionHtml": "<p>Boa</p>", "vendor": "FDC", "productType": "Moveis",
        "tags": ["sala", "azul"], "status": "ACTIVE", "publishedAt": "2026-09-01T12:00:00Z",
        "seo": {"title": "Poltrona azul barata", "description": "A melhor poltrona"},
        "collections": {"nodes": [{"id": "gid://shopify/Collection/3"},
                                  {"id": "gid://shopify/Collection/99"}],
                        "pageInfo": {"hasNextPage": False}},
        "media": {"nodes": []},
        "variants": {"nodes": [{
            "id": "gid://shopify/ProductVariant/701", "title": "Default Title",
            "sku": "POL-1", "barcode": "7891234567895", "price": "100.00",
            "compareAtPrice": None, "inventoryQuantity": 5, "inventoryPolicy": "CONTINUE",
            "taxable": False, "position": 1,
            "inventoryItem": {"tracked": True, "requiresShipping": False,
                              "measurement": {"weight": {"value": 2.5, "unit": "KILOGRAMS"}}},
            "selectedOptions": [{"name": "Title", "value": "Default Title"}],
        }], "pageInfo": {"hasNextPage": False}},
    }
    return {**base, **extra}


class LojaFalsa:
    def __init__(self, resposta=None, erro=None):
        self.resposta, self.erro, self.pedidos = resposta, erro, []

    def __call__(self, _configuracao):
        return self

    def graphql(self, query, variables=None):
        self.pedidos.append(variables)
        if self.erro:
            raise self.erro
        return {"product": self.resposta}


def _webhook(conta, operacao, loja):
    configuracao = _configuracao(conta)
    corpo = {"id": 700, "admin_graphql_api_id": GID, "title": "Poltrona REST",
             "variants": [], "images": []}
    with patch("apps.shopify.produtos_busca.ShopifyClient", loja), \
            usando_configuracao(configuracao):
        processar_webhook(configuracao, "produtos", operacao, corpo, lambda *_: None)


def _categoria_shopify(numero, nome):
    categoria = Categoria.objects.create(nome=nome, slug=nome.lower())
    ExternalReference.objects.create(
        platform="shopify", entity_type="categorias", object_id=str(categoria.pk),
        external_id=f"gid://shopify/Collection/{numero}")
    return categoria


def _vinculo():
    return ExternalReference.objects.get(entity_type="produtos", external_id=GID)


@pytest.mark.django_db
def test_webhook_busca_o_produto_completo_e_grava_seo_descricao_tags_e_colecoes(conta):
    sala = _categoria_shopify(3, "Sala")
    loja = LojaFalsa(node())

    _webhook(conta, "create", loja)

    assert loja.pedidos == [{"id": GID}]
    produto = Produto.objects.get(slug="poltrona-azul")
    assert (produto.seo_titulo, produto.seo_descricao) == (
        "Poltrona azul barata", "A melhor poltrona")
    assert (produto.nome, produto.descricao, produto.fornecedor) == (
        "Poltrona", "<p>Boa</p>", "FDC")
    assert produto.status == Produto.Status.PUBLICADO
    assert produto.publicado_em.isoformat() == "2026-09-01T12:00:00+00:00"
    assert sorted(produto.tags.values_list("nome", flat=True)) == ["azul", "sala"]
    assert list(produto.categorias.all()) == [sala], "colecao 99 nao importada fica de fora"
    assert _vinculo().metadata["product_type"] == "Moveis"
    assert not produto.metadados, "dado do Shopify fica no vinculo, nao no produto"


@pytest.mark.django_db
def test_variante_recebe_barcode_peso_e_politicas(conta):
    _webhook(conta, "create", LojaFalsa(node()))

    variante = Produto.objects.get(slug="poltrona-azul").variante_padrao
    assert variante.barcode == "7891234567895"
    assert (variante.weight, variante.weight_unit) == (Decimal("2.500"), "kg")
    assert variante.taxable is False and variante.requires_shipping is False
    assert variante.inventory_policy == "continue" and variante.manage_inventory is True


@pytest.mark.django_db
def test_produto_que_ja_existe_e_atualizado_alem_das_imagens(conta):
    """Sincronizacao de produto ja vinculado: antes so as imagens eram atualizadas."""
    _webhook(conta, "create", LojaFalsa(node()))
    do_hub = Categoria.objects.create(nome="So no hub", slug="so-no-hub")
    produto = Produto.objects.get(slug="poltrona-azul")
    produto.categorias.add(do_hub)
    peso = {"weight": {"value": 1500, "unit": "GRAMS"}}
    variantes = node()["variants"]
    variantes["nodes"][0]["inventoryItem"]["measurement"] = peso

    recursos.produto(node(seo={"title": "Novo titulo", "description": "Nova"},
                          tags=["quarto"], descriptionHtml="<p>Nova</p>",
                          status="ARCHIVED", variants=variantes))

    produto.refresh_from_db()
    assert (produto.seo_titulo, produto.descricao) == ("Novo titulo", "<p>Nova</p>")
    assert produto.status == Produto.Status.ARQUIVADO
    assert list(produto.tags.values_list("nome", flat=True)) == ["quarto"]
    assert list(produto.categorias.all()) == [do_hub], "categoria sem vinculo continua"
    variante = produto.variante_padrao
    assert (variante.weight, variante.weight_unit) == (Decimal("1500.000"), "g")


@pytest.mark.django_db
def test_seo_vazio_na_loja_nao_apaga_o_seo_do_hub(conta):
    _webhook(conta, "create", LojaFalsa(node()))

    recursos.produto(node(seo={"title": None, "description": ""}))

    produto = Produto.objects.get(slug="poltrona-azul")
    assert produto.seo_titulo == "Poltrona azul barata"


@pytest.mark.django_db
def test_erro_de_rede_na_busca_sobe_para_a_execucao_ser_reprocessada(conta):
    with pytest.raises(ErroDeRede):
        _webhook(conta, "create", LojaFalsa(erro=ErroDeRede("timeout")))

    assert not Produto.objects.filter(slug="poltrona-azul").exists()


@pytest.mark.django_db
def test_sincronizacao_busca_inteiro_o_produto_com_variantes_cortadas(conta):
    """A pagina em lote traz ate 10 variantes; acima disso a busca de um produto completa."""
    from apps.shopify.sincronizar import CONVERSORES

    cortado = node(variants={"nodes": [], "pageInfo": {"hasNextPage": True}})
    loja = LojaFalsa(node())
    with patch("apps.shopify.produtos_busca.ShopifyClient", loja), \
            usando_configuracao(_configuracao(conta)):
        completo = CONVERSORES["produtos"](cortado)
        inteiro = CONVERSORES["produtos"](node())

    assert completo["variants"]["nodes"][0]["sku"] == "POL-1"
    assert loja.pedidos == [{"id": GID}], "produto inteiro na pagina nao gasta outra consulta"
    assert inteiro["handle"] == "poltrona-azul"


def test_consulta_em_lote_pede_seo_e_cabe_no_limite_de_custo():
    from apps.shopify.consultas import CONSULTAS

    consulta = " ".join(CONSULTAS["produtos"][1].split())
    for campo in ("seo { title description }", "descriptionHtml", "vendor", "productType",
                  "tags", "publishedAt", "collections(first: 10)", "barcode", "taxable",
                  "inventoryPolicy", "measurement { weight { value unit } }",
                  "products(first: 10"):
        assert campo in consulta
