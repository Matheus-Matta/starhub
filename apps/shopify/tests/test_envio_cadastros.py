"""Envio de clientes e categorias do hub para o Shopify."""

import pytest

from apps.loja.models import Categoria, Cliente
from apps.shopify.cliente import ShopifyErro
from apps.shopify.envio.categorias import CategoriaShopify
from apps.shopify.envio.clientes import ClienteShopify, telefone_e164
from apps.shopify.tests.envio_falso import enviador

pytestmark = pytest.mark.django_db
OK = {"userErrors": []}


def test_cliente_criar_envia_dados_e_devolve_gid():
    """Sem o gid devolvido o vinculo nao e gravado e todo update duplicaria o cliente."""
    cliente = Cliente.objects.create(email="a@x.com", nome="Ana", sobrenome="Lima",
                                     telefone="(11) 98888-7777", aceita_marketing=True)
    env, falso = enviador(ClienteShopify, customerCreate={
        **OK, "customer": {"id": "gid://shopify/Customer/7"}})
    assert env.criar(cliente) == "gid://shopify/Customer/7"
    entrada = falso.chamadas[0][1]["input"]
    assert entrada["email"] == "a@x.com" and entrada["firstName"] == "Ana"
    assert entrada["phone"] == "+5511988887777"
    assert entrada["emailMarketingConsent"]["marketingState"] == "SUBSCRIBED"


def test_cliente_atualizar_usa_gid_e_descarta_telefone_invalido():
    """Telefone fora do E.164 faria o Shopify recusar o cliente inteiro."""
    cliente = Cliente.objects.create(email="a@x.com", telefone="12345678")
    env, falso = enviador(ClienteShopify, customerUpdate=OK,
                          customerEmailMarketingConsentUpdate=OK)
    env.atualizar(cliente, "7")
    entrada = falso.chamadas[0][1]["input"]
    assert entrada["id"] == "gid://shopify/Customer/7"
    assert "phone" not in entrada
    consentimento = falso.chamadas[1][1]["input"]["emailMarketingConsent"]
    assert consentimento["marketingState"] == "UNSUBSCRIBED"


def test_cliente_excluir_chama_customer_delete():
    env, falso = enviador(ClienteShopify, customerDelete=OK)
    env.excluir("gid://shopify/Customer/7")
    assert falso.chamadas[0][1] == {"input": {"id": "gid://shopify/Customer/7"}}


def test_cliente_erro_do_shopify_vira_excecao():
    """userErrors vem com HTTP 200; engolir daria o envio como feito."""
    cliente = Cliente.objects.create(email="a@x.com")
    env, _ = enviador(ClienteShopify, customerCreate={
        "customer": None, "userErrors": [{"field": ["email"], "message": "ja usado"}]})
    with pytest.raises(ShopifyErro, match="ja usado"):
        env.criar(cliente)


@pytest.mark.parametrize("bruto,esperado", [
    ("+55 11 98888-7777", "+5511988887777"), ("1133334444", "+551133334444"),
    ("5511988887777", "+5511988887777"), ("", None), ("12", None),
])
def test_telefone_e164(bruto, esperado):
    assert telefone_e164(bruto) == esperado


def test_categoria_criar_envia_titulo_descricao_e_imagem():
    categoria = Categoria.objects.create(
        nome="Poltronas", slug="poltronas", descricao="<p>Conforto</p>",
        imagem={"src": "https://cdn.x/p.jpg", "alt": "Poltrona"})
    env, falso = enviador(CategoriaShopify, collectionCreate={
        **OK, "collection": {"id": "gid://shopify/Collection/3"}})
    assert env.criar(categoria) == "gid://shopify/Collection/3"
    assert falso.chamadas[0][1]["colecao"] == {
        "title": "Poltronas", "descriptionHtml": "<p>Conforto</p>",
        "image": {"src": "https://cdn.x/p.jpg", "altText": "Poltrona"}}


def test_categoria_sem_imagem_nao_manda_image():
    categoria = Categoria.objects.create(nome="Mesas", slug="mesas")
    env, falso = enviador(CategoriaShopify, collectionUpdate=OK)
    env.atualizar(categoria, "3")
    entrada = falso.chamadas[0][1]["colecao"]
    assert entrada["id"] == "gid://shopify/Collection/3" and "image" not in entrada


def test_categoria_excluir_chama_collection_delete():
    env, falso = enviador(CategoriaShopify, collectionDelete=OK)
    env.excluir("3")
    assert falso.chamadas[0][1] == {"input": {"id": "gid://shopify/Collection/3"}}


def test_cliente_atualizar_manda_consentimento_na_mutation_propria():
    """A doc 2026-07 do customerUpdate: "To set marketing consent, use the
    customerEmailMarketingConsentUpdate ... mutations instead". Mandar no update o recusa."""
    cliente = Cliente.objects.create(email="a@x.com", aceita_marketing=True)
    env, falso = enviador(ClienteShopify, customerUpdate=OK,
                          customerEmailMarketingConsentUpdate=OK)
    env.atualizar(cliente, "7")
    assert "emailMarketingConsent" not in falso.chamadas[0][1]["input"]
    query, variaveis = falso.chamadas[1]
    assert "customerEmailMarketingConsentUpdate" in query
    assert variaveis["input"]["customerId"] == "gid://shopify/Customer/7"
    assert variaveis["input"]["emailMarketingConsent"]["marketingState"] == "SUBSCRIBED"


def test_categoria_usa_o_argumento_collection_e_nao_o_input_deprecado():
    """`input: CollectionInput` esta deprecado na 2026-07; o atual e `collection`."""
    categoria = Categoria.objects.create(nome="Mesas", slug="mesas")
    env, falso = enviador(CategoriaShopify, collectionUpdate=OK)
    env.atualizar(categoria, "3")
    query, variaveis = falso.chamadas[0]
    assert "CollectionUpdateInput!" in query and "collection: $colecao" in query
    assert variaveis["colecao"]["id"] == "gid://shopify/Collection/3"
