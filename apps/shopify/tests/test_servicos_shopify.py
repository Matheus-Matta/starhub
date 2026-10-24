"""Servicos do hub na Shopify: produto escondido, bloco do tema e pedido."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.core.models import ExternalReference
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import RegraServico, Servico
from apps.loja.services.extras_pedido import extras
from apps.loja.services.variantes import criar_produto
from apps.shopify import recursos
from apps.shopify.contexto import usando_configuracao
from apps.shopify.envio.marketplace import ShopifyMarketplace
from apps.shopify.pedidos import importar_pedido
from apps.shopify.servicos_envio import ServicoShopify
from apps.shopify.tests.envio_falso import GraphQLFalso
from apps.shopify.tests.pedido_exemplo import pedido_shopify, produto_shopify_falso  # noqa: F401

pytestmark = pytest.mark.django_db
PRODUTO_GID = "gid://shopify/Product/700"
ORIGEM = "https://loja.myshopify.com"


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    """Nenhum teste daqui fala com a Shopify real: so os falsos de cada teste."""
    def recusar(*_args, **_kwargs):
        raise AssertionError("chamada de rede a Shopify num teste")

    monkeypatch.setattr("apps.shopify.cliente.ShopifyClient.graphql", recusar)


@pytest.fixture
def cfg(conta):
    return ConfiguracaoIntegracao.objects.create(
        account=conta, plataforma="shopify", dominio_loja="loja.myshopify.com",
        enviar_servicos=True, receber_servicos=True, servicos_no_tema=True)


@pytest.fixture
def sofa():
    produto = criar_produto("Sofa", sku="SOF-1", price=Decimal("1500.00"))
    ExternalReference.objects.create(platform="shopify", entity_type="produtos",
                                     external_id="gid://shopify/Product/111",
                                     object_id=str(produto.pk))
    return produto


@pytest.fixture
def montagem(sofa):
    servico = Servico.objects.create(nome="Montagem", sku="SERV-MONT", preco=Decimal("120.00"))
    regra = RegraServico.objects.create(servico=servico, tipo=RegraServico.Tipo.PRODUTO,
                                        preco=Decimal("80.00"))
    regra.produtos.set([sofa])
    return servico


def _exportar(cfg, servico):
    falso = GraphQLFalso({
        "productSet": {"product": {"id": PRODUTO_GID, "variants": {"nodes": [
            {"id": "gid://shopify/ProductVariant/801", "price": "80.00"},
            {"id": "gid://shopify/ProductVariant/802", "price": "120.00"}]}},
            "userErrors": []},
        "publications": {"nodes": [{"id": "gid://shopify/Publication/1", "name": "POS"},
                                   {"id": "gid://shopify/Publication/2",
                                    "name": "Online Store"}]},
        "publishablePublish": {"userErrors": []},
    })
    enviador = ShopifyMarketplace(cfg).enviador("servicos")
    enviador._cliente = falso
    enviador.enviar("create", servico.pk)
    return falso


def test_servico_vira_produto_escondido_com_uma_variante_por_preco(cfg, montagem):
    """A Shopify so cobra item do carrinho; cada preco de regra precisa da sua variante."""
    falso = _exportar(cfg, montagem)

    entrada = falso.chamadas[0][1]["input"]
    assert entrada["tags"] == ["starhub-servico"] and entrada["title"] == "Montagem"
    assert [v["price"] for v in entrada["variants"]] == ["80.00", "120.00"]
    assert {v["sku"] for v in entrada["variants"]} == {"SERV-MONT"}
    assert entrada["variants"][0]["inventoryItem"] == {"tracked": False,
                                                       "requiresShipping": False}
    assert entrada["metafields"][0]["key"] == "hidden"
    assert falso.chamadas[-1][1]["input"] == [{"publicationId": "gid://shopify/Publication/2"}]
    assert ExternalReference.objects.filter(entity_type="servicos_variantes").count() == 2


def test_enviar_servicos_desligado_nao_manda_nada(cfg, montagem):
    cfg.enviar_servicos = False
    assert "desligado" in ShopifyMarketplace(cfg).enviar("servicos", "create", montagem.pk)


def test_bloco_do_tema_recebe_a_variante_do_preco_da_regra(client, cfg, sofa, montagem):
    _exportar(cfg, montagem)
    url = reverse("shopify_servicos_publico", args=[cfg.uuid])

    resposta = client.get(url, {"produto": "111"}, headers={"Origin": ORIGEM})

    assert resposta.status_code == 200 and resposta["Access-Control-Allow-Origin"] == ORIGEM
    assert resposta.json()["servicos"] == [{
        "id": montagem.pk, "nome": "Montagem", "preco": "80.00",
        "preco_texto": "R$ 80,00", "variante": 801}]


def test_bloco_do_tema_desligado_ou_de_outro_dominio_nao_mostra_servico(
        client, cfg, sofa, montagem):
    _exportar(cfg, montagem)
    url = reverse("shopify_servicos_publico", args=[cfg.uuid])
    assert client.get(url, {"produto": "111"},
                      headers={"Origin": "https://outra.com"}).status_code == 403
    cfg.servicos_no_tema = False
    cfg.save()
    assert client.get(url, {"produto": "111"},
                      headers={"Origin": ORIGEM}).json() == {"servicos": []}


def _pedido():
    vinculo = [{"name": "_starhub_vinculo", "value": "abc"}]
    return pedido_shopify(discount_codes=[], discount_applications=[], line_items=[
        {"id": 901, "title": "Sofa", "sku": "SOF-1", "product_id": 111, "variant_id": 9001,
         "quantity": 1, "price": "1500.00", "discount_allocations": [], "tax_lines": [],
         "properties": vinculo},
        {"id": 902, "title": "Montagem", "sku": "SERV-MONT", "product_id": 700,
         "variant_id": 801, "quantity": 1, "price": "80.00", "discount_allocations": [],
         "tax_lines": [], "requires_shipping": False, "properties": vinculo}])


@pytest.mark.usefixtures("produto_shopify_falso")
def test_linha_do_servico_vira_servico_do_item_com_o_valor_somado(cfg, sofa, montagem):
    """Sem isto o servico virava item solto (e um produto Montagem no catalogo)."""
    _exportar(cfg, montagem)

    with usando_configuracao(cfg):
        pedido, _ = importar_pedido(_pedido())

    item = pedido.itens.get()
    assert item.sku == "SOF-1" and item.total == Decimal("1580.00")
    servico = next(s for s in extras(pedido)["servicos"] if s.get("servico_id") == montagem.pk)
    assert servico | {"item_id": item.pk} == servico and servico["preco"] == "80.00"


def test_produto_servico_nunca_vira_produto_do_catalogo():
    assert recursos.produto({"id": "gid://shopify/Product/9", "title": "Garantia",
                             "tags": ["starhub-servico"]}) == (None, False)


def test_servico_e_regra_novos_vao_numa_tarefa_so_para_a_shopify(
        cfg, monkeypatch, django_capture_on_commit_callbacks):
    """A regra muda os precos (variantes); o servico e a regra salvos juntos sao um envio."""
    enfileirados = []
    monkeypatch.setattr("apps.shopify.servicos_sinais._enfileirar",
                        lambda *args: enfileirados.append(args))

    with django_capture_on_commit_callbacks(execute=True):
        garantia = Servico.objects.create(nome="Garantia", sku="SERV-GAR")
        RegraServico.objects.create(servico=garantia, preco=Decimal("90.00"))

    assert [(r, o, pk) for _c, r, o, pk in enfileirados] == [
        ("servicos", "create", str(garantia.pk))]


def test_servico_excluido_sai_da_shopify(cfg, montagem):
    _exportar(cfg, montagem)
    falso = GraphQLFalso({"productDelete": {"deletedProductId": PRODUTO_GID,
                                            "userErrors": []}})
    enviador = ServicoShopify(ShopifyMarketplace(cfg))
    enviador._cliente = falso
    pk = montagem.pk
    montagem.delete()

    enviador.enviar("delete", pk)

    assert falso.chamadas[0][1] == {"input": {"id": PRODUTO_GID}}
    assert not ExternalReference.objects.filter(entity_type__startswith="servicos").exists()
