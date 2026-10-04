import pytest

from apps.core.models import ExternalReference, Origin
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.loja.models import Produto
from apps.loja.services.variantes import criar_produto
from apps.shopify import pedidos_produtos
from apps.shopify.cliente import ShopifyErro
from apps.shopify.contexto import configuracao_atual, usando_configuracao
from apps.shopify.pedidos_produtos import garantir_produto
from apps.shopify.tasks import sincronizar_shopify

NODE = {
    "id": "gid://shopify/Product/987", "title": "Sofa Retratil", "handle": "sofa-retratil",
    "status": "ACTIVE", "vendor": "Moveis FDC", "bodyHtml": "<p>Sofa</p>",
    "media": {"nodes": []},
    "variants": {"nodes": [
        {"id": "gid://shopify/ProductVariant/31", "title": "Bege", "sku": "SOFA-BEGE",
         "price": "1800.00", "compareAtPrice": "2000.00", "inventoryQuantity": 3,
         "selectedOptions": [{"name": "Cor", "value": "Bege"}]},
        {"id": "gid://shopify/ProductVariant/32", "title": "Prata", "sku": "SOFA-PRATA",
         "price": "1999.99", "compareAtPrice": None, "inventoryQuantity": 14,
         "selectedOptions": [{"name": "Cor", "value": "Prata"}]},
    ]},
}

LINHA = {"id": 777, "product_id": 987, "variant_id": 32, "sku": "SOFA-PRATA",
         "title": "Sofa Retratil", "price": "1999.99", "quantity": 1}


class ClienteFalso:
    chamadas = []
    resposta = {"product": NODE}
    erro = None

    def __init__(self, configuracao):
        self.configuracao = configuracao

    def graphql(self, query, variables=None):
        ClienteFalso.chamadas.append(variables)
        if ClienteFalso.erro:
            raise ClienteFalso.erro
        return ClienteFalso.resposta


@pytest.fixture
def cliente(monkeypatch, conta):
    ClienteFalso.chamadas, ClienteFalso.resposta, ClienteFalso.erro = [], {"product": NODE}, None
    monkeypatch.setattr(pedidos_produtos, "ShopifyClient", ClienteFalso)
    configuracao = ConfiguracaoIntegracao.objects.create(nome="Loja", plataforma="shopify")
    with usando_configuracao(configuracao):
        yield ClienteFalso


@pytest.mark.django_db
def test_produto_desconhecido_e_importado_completo_e_devolve_a_variante_do_item(cliente):
    """Item de produto novo nao pode virar cadastro minimo: o produto vem inteiro do Shopify."""
    variante = garantir_produto(LINHA)

    produto = Produto.objects.get(slug="sofa-retratil")
    assert cliente.chamadas == [{"id": "gid://shopify/Product/987"}]
    assert produto.variantes.count() == 2
    assert variante.sku == "SOFA-PRATA"
    assert str(variante.price) == "1999.99"
    assert ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type="produtos", external_id=NODE["id"]
    ).exists()


@pytest.mark.django_db
def test_mesmo_produto_repetido_no_pedido_busca_no_shopify_uma_vez_so(cliente):
    """Pedido com duas linhas do mesmo produto nao pode importar (nem consultar) duas vezes."""
    primeira = garantir_produto(LINHA)
    segunda = garantir_produto({**LINHA, "variant_id": 31, "sku": "SOFA-BEGE"})

    assert len(cliente.chamadas) == 1
    assert primeira.produto_id == segunda.produto_id
    assert segunda.sku == "SOFA-BEGE"


@pytest.mark.django_db
def test_produto_ja_cadastrado_pelo_sku_nao_chama_a_api(cliente):
    """Achar o produto localmente precisa bastar; consulta externa custa cota da API."""
    produto = criar_produto("Sofa local", sku="SOFA-PRATA")

    variante = garantir_produto(LINHA)

    assert cliente.chamadas == []
    assert variante == produto.variante_padrao


@pytest.mark.django_db
def test_item_sem_product_id_fica_solto(cliente):
    """Item personalizado nao tem produto no Shopify; tentar buscar daria erro de consulta."""
    assert garantir_produto({**LINHA, "product_id": None, "sku": ""}) is None
    assert cliente.chamadas == []


@pytest.mark.django_db
def test_produto_apagado_no_shopify_devolve_none(cliente):
    """Produto removido volta null na API; nao pode quebrar a importacao do pedido."""
    cliente.resposta = {"product": None}

    assert garantir_produto(LINHA) is None
    assert Produto.objects.count() == 0


@pytest.mark.django_db
def test_erro_da_api_sobe_para_a_execucao_ser_reprocessada(cliente):
    """Engolir o erro gravaria o pedido com item solto para sempre por uma falha passageira."""
    cliente.erro = ShopifyErro("Shopify respondeu HTTP 503")

    with pytest.raises(ShopifyErro):
        garantir_produto(LINHA)


@pytest.mark.django_db
def test_sem_configuracao_no_contexto_devolve_none(monkeypatch):
    """Chamado fora de uma tarefa, nao ha loja para consultar: o item fica solto."""
    monkeypatch.setattr(pedidos_produtos, "ShopifyClient", ClienteFalso)
    ClienteFalso.chamadas = []

    assert garantir_produto(LINHA) is None
    assert ClienteFalso.chamadas == []


@pytest.mark.django_db
def test_tarefa_liga_a_configuracao_no_contexto(monkeypatch):
    """Sem o contexto ligado pela tarefa, o importador nunca acharia a loja para buscar."""
    configuracao = ConfiguracaoIntegracao.objects.create(nome="Loja", plataforma="shopify")
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR
    )
    vistas = []

    def sincronizar(_configuracao, _progresso):
        vistas.append(configuracao_atual())
        return "ok"

    monkeypatch.setattr("apps.shopify.tasks.sincronizar_loja", sincronizar)
    sincronizar_shopify.run(str(execucao.pk))

    assert [c.pk for c in vistas] == [configuracao.pk]
    assert configuracao_atual() is None
