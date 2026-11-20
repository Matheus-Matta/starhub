"""Produto ligado a um id que nao existe mais no Shopify (tarefa #100056, SOFA TORONTO).

O update falhava com "id: Product does not exist" mesmo com o SKU na loja. Agora o
hub acha o produto da loja pelo SKU e refaz o vinculo; sem SKU na loja, cria de novo
(se Enviar > Produtos > Criar estiver ligado).
"""

import pytest

from apps.core.models import ExternalReference
from apps.shopify.cliente import ShopifyErro
from apps.shopify.tests.test_envio_produtos import _enviador, _simples
from apps.shopify.tests.test_envio_produtos_atualizar import BULK_UPDATE, LOCAL

VELHO = "gid://shopify/Product/9142785146998"
NOVO = "gid://shopify/Product/777"
SUMIU = {"productUpdate": {"product": None, "userErrors": [
    {"field": ["id"], "message": "Product does not exist"}]}}


def _ok(gid):
    return {"productUpdate": {"product": {
        "id": gid, "media": {"nodes": []}, "options": [{"name": "Title"}],
        "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/5", "sku": "MESA-1",
                                "inventoryItem": {"id": "gid://shopify/InventoryItem/5"}}]},
    }, "userErrors": []}}


class Sequencia:
    """Como o ClienteFalso, mas a mesma raiz pode responder diferente a cada chamada."""

    def __init__(self, respostas):
        self.respostas, self.chamadas = respostas, []

    def graphql(self, query, variables=None):
        self.chamadas.append((query, variables))
        for chave, resposta in self.respostas.items():
            if chave in query:
                return resposta.pop(0) if isinstance(resposta, list) else resposta
        if "node(id:" in query:
            # Fotos do produto achado pelo SKU (produtos_midias_religar): sem resposta no
            # teste, a loja nao tem nenhuma.
            return {"node": {"id": (variables or {}).get("id"), "media": {"nodes": []}}}
        if "product(id:" in query:
            # Conferencia do produto antes do update (produtos_religar.conferir): sem
            # resposta no teste, a loja nao informa SKU e o envio segue pelo id.
            return {"product": {"id": (variables or {}).get("id"), "variants": {"nodes": []}}}
        raise AssertionError(f"query inesperada: {query[:60]}")


def _preparar(conta, respostas, criar=False):
    produto, variante = _simples()
    enviador = _enviador(conta, {})
    enviador._cliente = Sequencia({"location": LOCAL, **respostas})
    if criar:
        enviador.configuracao.permissoes["enviar"]["produtos"]["create"] = True
        enviador.configuracao.save()
    for entidade, externo, obj in (("produtos", VELHO, produto),
                                   ("variantes", "gid://shopify/ProductVariant/1", variante)):
        ExternalReference.objects.create(platform="shopify", entity_type=entidade,
                                         object_id=str(obj.pk), external_id=externo)
    return produto, enviador


def _vinculo_do_produto(produto):
    return list(ExternalReference.objects.filter(
        entity_type="produtos", object_id=str(produto.pk)).values_list("external_id", flat=True))


def _sku(*produtos):
    return {"productVariants": {"nodes": [{"product": {"id": gid}} for gid in produtos]}}


@pytest.mark.django_db
def test_id_que_sumiu_acha_o_produto_da_loja_pelo_sku_e_atualiza(conta):
    produto, enviador = _preparar(conta, {
        "productUpdate": [SUMIU, _ok(NOVO)], "productVariants(": _sku(NOVO),
        "productVariantsBulkUpdate": BULK_UPDATE})

    enviador.atualizar(produto, VELHO)

    updates = [v for q, v in enviador.cliente.chamadas if "productUpdate" in q]
    assert [u["product"]["id"] for u in updates] == [VELHO, NOVO]
    assert _vinculo_do_produto(produto) == [NOVO]
    lote = next(v for q, v in enviador.cliente.chamadas if "productVariantsBulkUpdate" in q)
    assert lote["productId"] == NOVO
    assert lote["variants"][0]["id"] == "gid://shopify/ProductVariant/5"


@pytest.mark.django_db
def test_sem_o_sku_na_loja_cria_de_novo_quando_criar_esta_ligado(conta):
    criado = {"productSet": {"product": {
        "id": NOVO, "media": {"nodes": []},
        "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/9", "position": 1,
                                "inventoryItem": {"id": "gid://shopify/InventoryItem/9"}}]},
    }, "userErrors": []}}
    produto, enviador = _preparar(conta, {
        "productUpdate": [SUMIU], "productVariants(": _sku(), "productSet": criado},
        criar=True)

    enviador.atualizar(produto, VELHO)

    assert _vinculo_do_produto(produto) == [NOVO]


@pytest.mark.django_db
def test_sem_o_sku_e_com_criar_desligado_explica_o_que_fazer(conta):
    produto, enviador = _preparar(conta, {"productUpdate": [SUMIU],
                                          "productVariants(": _sku()})

    with pytest.raises(ShopifyErro, match="Enviar > Produtos > Criar"):
        enviador.atualizar(produto, VELHO)

    assert _vinculo_do_produto(produto) == [VELHO]


@pytest.mark.django_db
def test_sku_em_produto_da_loja_que_ja_e_de_outro_produto_do_hub_nao_rouba(conta):
    produto, enviador = _preparar(conta, {"productUpdate": [SUMIU],
                                          "productVariants(": _sku(NOVO)})
    ExternalReference.objects.create(platform="shopify", entity_type="produtos",
                                     object_id="999999", external_id=NOVO)

    with pytest.raises(ShopifyErro, match="SKU repetido"):
        enviador.atualizar(produto, VELHO)

    assert _vinculo_do_produto(produto) == [VELHO]


@pytest.mark.django_db
def test_outro_erro_do_shopify_continua_como_veio(conta):
    outro = {"productUpdate": {"product": None, "userErrors": [
        {"field": ["title"], "message": "Title is too long"}]}}
    produto, enviador = _preparar(conta, {"productUpdate": [outro]})

    with pytest.raises(ShopifyErro, match="Title is too long"):
        enviador.atualizar(produto, VELHO)
