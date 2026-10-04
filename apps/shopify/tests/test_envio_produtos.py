"""Envio de produto do hub para o Shopify (productSet / productDelete), sem rede."""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.integracoes import permissoes
from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import (
    Produto,
    Tag,
    TipoVariante,
    ValorDaVarianteProduto,
    ValorVariante,
    VarianteProduto,
)
from apps.shopify.cliente import ShopifyErro
from apps.shopify.envio.marketplace import ShopifyMarketplace

PRODUTO_GID = "gid://shopify/Product/900"


class ClienteFalso:
    """Responde cada chamada pela raiz da query e guarda o que foi enviado."""

    def __init__(self, respostas):
        self.respostas = respostas
        self.chamadas = []

    def graphql(self, query, variables=None):
        self.chamadas.append((query, variables))
        for chave, resposta in self.respostas.items():
            if chave in query:
                return resposta
        raise AssertionError(f"query inesperada: {query[:60]}")


def _variantes_resposta(*itens):
    return {"nodes": [
        {"id": f"gid://shopify/ProductVariant/{n}", "position": n,
         "inventoryItem": {"id": f"gid://shopify/InventoryItem/{n}"}}
        for n in itens
    ]}


def _enviador(conta, respostas):
    configuracao = ConfiguracaoIntegracao.objects.create(
        account=conta, plataforma="shopify", permissoes=permissoes.matriz_vazia()
    )
    enviador = ShopifyMarketplace(configuracao).enviador("produtos")
    enviador._cliente = ClienteFalso(respostas)
    return enviador


def _resposta_set(*variantes):
    return {"productSet": {
        "product": {"id": PRODUTO_GID, "variants": _variantes_resposta(*variantes)},
        "userErrors": [],
    }}


def _simples():
    produto = Produto.objects.create(
        nome="Mesa", descricao="<p>Mesa boa</p>", fornecedor="Moveis FDC"
    )
    variante = produto.variante_padrao
    variante.sku, variante.price, variante.sale_price = "MESA-1", Decimal("100.00"), Decimal("80")
    variante.inventory_quantity = 7
    variante.save()
    produto.tags.add(Tag.objects.create(nome="sala"))
    return produto, variante


@pytest.mark.django_db
def test_criar_produto_simples_manda_preco_de_venda_e_de_comparacao_como_texto(conta):
    """Preco promocional do hub e o `price` do Shopify; o normal vira `compareAtPrice`.

    Invertido, a loja venderia pelo preco cheio e mostraria o promocional riscado.
    """
    produto, variante = _simples()
    enviador = _enviador(conta, {
        "location": {"location": {"id": "gid://shopify/Location/1"}},
        "productSet": _resposta_set(1),
    })

    assert enviador.criar(produto) == PRODUTO_GID

    _, variaveis = enviador.cliente.chamadas[-1]
    entrada = variaveis["input"]
    assert variaveis.get("identifier") is None
    assert entrada["title"] == "Mesa"
    assert entrada["descriptionHtml"] == "<p>Mesa boa</p>"
    assert entrada["vendor"] == "Moveis FDC"
    assert entrada["status"] == "ACTIVE"
    assert entrada["tags"] == ["sala"]
    assert entrada["productOptions"] == [{"name": "Title", "values": [{"name": "Default Title"}]}]
    [enviada] = entrada["variants"]
    assert enviada["price"] == "80.00"
    assert enviada["compareAtPrice"] == "100.00"
    assert enviada["sku"] == "MESA-1"
    assert enviada["optionValues"] == [{"optionName": "Title", "name": "Default Title"}]
    assert enviada["inventoryQuantities"] == [
        {"locationId": "gid://shopify/Location/1", "name": "available", "quantity": 7}
    ]
    referencia = ExternalReference.objects.get(entity_type="variantes")
    assert referencia.object_id == str(variante.pk)
    assert referencia.external_id == "gid://shopify/ProductVariant/1"
    assert referencia.external_parent_id == PRODUTO_GID
    assert referencia.metadata["inventory_item_id"] == "gid://shopify/InventoryItem/1"


@pytest.mark.django_db
def test_criar_produto_variavel_manda_as_opcoes_de_cada_variante(conta):
    """Sem as opcoes o Shopify recusa duas variantes iguais ("Default Title" repetido)."""
    produto = Produto.objects.create(nome="Sofa", tipo=Produto.Tipo.VARIAVEL)
    cor = TipoVariante.objects.create(nome="Cor")
    for posicao, nome in enumerate(["Bege", "Prata"]):
        variante = VarianteProduto.objects.create(
            produto=produto, titulo=nome, price=Decimal("10"), posicao=posicao,
            manage_inventory=False,
        )
        ValorDaVarianteProduto.objects.create(
            variante=variante, valor=ValorVariante.objects.create(tipo=cor, valor=nome)
        )
    enviador = _enviador(conta, {"productSet": _resposta_set(1, 2)})

    enviador.criar(produto)

    entrada = enviador.cliente.chamadas[-1][1]["input"]
    assert entrada["productOptions"] == [
        {"name": "Cor", "values": [{"name": "Bege"}, {"name": "Prata"}]}
    ]
    assert [v["optionValues"] for v in entrada["variants"]] == [
        [{"optionName": "Cor", "name": "Bege"}], [{"optionName": "Cor", "name": "Prata"}]
    ]
    assert "inventoryQuantities" not in entrada["variants"][0]
    assert ExternalReference.objects.filter(entity_type="variantes").count() == 2


@pytest.mark.django_db
def test_excluir_usa_product_delete_com_o_gid(conta):
    """Exclusao no hub apaga o produto na loja; id numerico vira gid."""
    enviador = _enviador(conta, {"productDelete": {"productDelete": {
        "deletedProductId": PRODUTO_GID, "userErrors": []}}})

    enviador.excluir("900")

    assert enviador.cliente.chamadas[-1][1] == {"input": {"id": PRODUTO_GID}}


@pytest.mark.django_db
def test_user_errors_do_shopify_viram_shopify_erro(conta):
    """HTTP 200 com userErrors e recusa: o envio nao pode ser dado como feito."""
    produto, _ = _simples()
    enviador = _enviador(conta, {
        "location": {"location": {"id": "gid://shopify/Location/1"}},
        "productSet": {"productSet": {"product": None, "userErrors": [
            {"field": ["input", "title"], "message": "Title can't be blank"}]}},
    })

    with pytest.raises(ShopifyErro, match="input.title: Title can't be blank"):
        enviador.criar(produto)


@pytest.mark.django_db
def test_produto_sem_variante_nao_e_enviado(conta):
    """Bundle nao tem variante propria; o Shopify exige ao menos uma."""
    produto = Produto.objects.create(nome="Kit", tipo=Produto.Tipo.BUNDLE)
    enviador = _enviador(conta, {})

    with pytest.raises(EnvioNaoSuportado):
        enviador.criar(produto)
    assert enviador.cliente.chamadas == []
