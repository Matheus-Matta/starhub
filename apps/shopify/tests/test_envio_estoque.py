"""Envio do estoque da variante para o Shopify (inventorySetQuantities), sem rede."""

import pytest

from apps.core.models import ExternalReference
from apps.integracoes import permissoes
from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.integracoes.envio.registro import obter
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Produto
from apps.shopify.cliente import ShopifyErro
from apps.shopify.envio.marketplace import ShopifyMarketplace

VARIANTE_GID = "gid://shopify/ProductVariant/55"
ITEM_GID = "gid://shopify/InventoryItem/77"
LOCAL_GID = "gid://shopify/Location/1"


class ClienteFalso:
    def __init__(self, respostas):
        self.respostas = respostas
        self.chamadas = []

    def graphql(self, query, variables=None):
        self.chamadas.append((query, variables))
        for chave, resposta in self.respostas.items():
            if chave in query:
                return resposta
        raise AssertionError(f"query inesperada: {query[:60]}")


OK = {"inventorySetQuantities": {"inventoryAdjustmentGroup": {}, "userErrors": []}}
LOCAL = {"location": {"id": LOCAL_GID}}


def _enviador(conta, respostas):
    configuracao = ConfiguracaoIntegracao.objects.create(
        account=conta, plataforma="shopify", permissoes=permissoes.matriz_vazia()
    )
    enviador = ShopifyMarketplace(configuracao).enviador("estoque")
    enviador._cliente = ClienteFalso(respostas)
    return enviador


def _variante(quantidade=12, metadata=None):
    variante = Produto.objects.create(nome="Mesa").variante_padrao
    variante.inventory_quantity = quantidade
    variante.save()
    ExternalReference.objects.create(
        platform="shopify", entity_type="variantes", object_id=str(variante.pk),
        external_id=VARIANTE_GID, metadata=metadata or {},
    )
    return variante


@pytest.mark.django_db
def test_atualizar_define_a_quantidade_disponivel_no_local_principal(conta):
    """O hub manda o numero absoluto: o Shopify fica igual ao hub, sem somar delta."""
    variante = _variante(metadata={"inventory_item_id": ITEM_GID})
    enviador = _enviador(conta, {"inventorySetQuantities": OK, "location": LOCAL})

    enviador.atualizar(variante, VARIANTE_GID)

    query, variaveis = enviador.cliente.chamadas[-1]
    assert "@idempotent(key: $idempotencyKey)" in query
    assert variaveis["idempotencyKey"]
    entrada = variaveis["input"]
    assert entrada["name"] == "available"
    assert entrada["reason"] == "correction"
    assert entrada["referenceDocumentUri"] == f"gid://starhub/VarianteProduto/{variante.pk}"
    assert entrada["quantities"] == [{
        "inventoryItemId": ITEM_GID, "locationId": LOCAL_GID,
        "quantity": 12, "changeFromQuantity": None,
    }]


@pytest.mark.django_db
def test_sem_inventory_item_guardado_busca_pela_variante(conta):
    """Variante vinda do import nao guardou o inventoryItem: consulta uma vez e guarda."""
    variante = _variante()
    enviador = _enviador(conta, {
        "inventorySetQuantities": OK,
        "productVariant": {"productVariant": {"inventoryItem": {"id": ITEM_GID}}},
        "location": LOCAL,
    })

    enviador.atualizar(variante, VARIANTE_GID)

    assert enviador.cliente.chamadas[-1][1]["input"]["quantities"][0]["inventoryItemId"] == ITEM_GID
    referencia = ExternalReference.objects.get(external_id=VARIANTE_GID)
    assert referencia.metadata["inventory_item_id"] == ITEM_GID


@pytest.mark.django_db
def test_estoque_negativo_do_hub_vai_como_esta(conta):
    """Venda sob encomenda deixa saldo negativo; zerar esconderia o que falta entregar."""
    variante = _variante(quantidade=-2, metadata={"inventory_item_id": ITEM_GID})
    enviador = _enviador(conta, {"inventorySetQuantities": OK, "location": LOCAL})

    enviador.atualizar(variante, VARIANTE_GID)

    assert enviador.cliente.chamadas[-1][1]["input"]["quantities"][0]["quantity"] == -2


@pytest.mark.django_db
def test_variante_sem_controle_de_estoque_nao_e_enviada(conta):
    """Item nao rastreado no Shopify recusa quantidade: e ignorado, nao falha."""
    variante = _variante(metadata={"inventory_item_id": ITEM_GID})
    variante.manage_inventory = False
    variante.save()
    enviador = _enviador(conta, {})

    with pytest.raises(EnvioNaoSuportado):
        enviador.atualizar(variante, VARIANTE_GID)
    assert enviador.cliente.chamadas == []


@pytest.mark.django_db
def test_criar_e_excluir_estoque_nao_sao_suportados(conta):
    """Estoque nasce e morre com a variante (recurso produtos), nunca sozinho."""
    variante = _variante()
    enviador = _enviador(conta, {})

    with pytest.raises(EnvioNaoSuportado):
        enviador.criar(variante)
    with pytest.raises(EnvioNaoSuportado):
        enviador.excluir(VARIANTE_GID)


@pytest.mark.django_db
def test_user_errors_do_estoque_viram_shopify_erro(conta):
    """Item nao estocado no local principal volta em userErrors e precisa aparecer."""
    variante = _variante(metadata={"inventory_item_id": ITEM_GID})
    enviador = _enviador(conta, {"location": LOCAL, "inventorySetQuantities": {
        "inventorySetQuantities": {"userErrors": [
            {"field": ["input"], "message": "not stocked at location"}]}}})

    with pytest.raises(ShopifyErro, match="not stocked at location"):
        enviador.atualizar(variante, VARIANTE_GID)


def test_marketplace_shopify_fica_registrado_com_os_sete_recursos():
    """Sem o registro no ready() o distribuidor nao acha o Shopify e nada e enviado."""
    assert obter("shopify") is ShopifyMarketplace
    assert {classe.recurso for classe in ShopifyMarketplace.recursos} == {
        "produtos", "estoque", "clientes", "categorias", "cupons", "pedidos", "avaliacoes",
    }


@pytest.mark.django_db
def test_envio_pelo_marketplace_acha_a_variante_pelo_vinculo_de_variantes(conta):
    """O estoque usa o vinculo "variantes" do import; com outra entidade seria ignorado."""
    variante = _variante(metadata={"inventory_item_id": ITEM_GID})
    matriz = permissoes.matriz_vazia()
    matriz["enviar"]["estoque"]["update"] = True
    configuracao = ConfiguracaoIntegracao.objects.create(
        account=conta, plataforma="shopify", permissoes=matriz
    )
    marketplace = ShopifyMarketplace(configuracao)
    marketplace.enviador("estoque")._cliente = ClienteFalso(
        {"inventorySetQuantities": OK, "location": LOCAL}
    )

    assert marketplace.enviar("estoque", "update", variante.pk) == "atualizado"
