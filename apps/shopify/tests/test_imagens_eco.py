"""Importacao de imagens do Shopify reconhecendo a foto que o proprio hub enviou.

O hub manda a URL dele; o Shopify rehospeda na CDN com outra URL e o webhook
products/update volta. Sem reconhecer a midia pelo vinculo, o hub baixava a foto
de novo e o produto ficava com a imagem duplicada.
"""

from unittest.mock import patch

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import MidiaProduto, Produto
from apps.shopify.imagens import sincronizar_imagens
from apps.shopify.tests.test_imagens_webhook import PNG, RespostaImagem

HUB = "https://hub.exemplo.com/media/produtos/mesa.png"
CDN = "https://cdn.shopify.com/s/files/1/mesa.png?v=1"


def _produto_com_foto_enviada(external_id="gid://shopify/MediaImage/555"):
    produto = Produto.objects.create(nome="Mesa")
    midia = MidiaProduto.objects.create(produto=produto, url=HUB, alt_text="Mesa")
    ExternalReference.objects.create(
        platform="shopify", entity_type="midias", object_id=str(midia.pk),
        external_id=external_id, metadata={"enviado_src": HUB},
    )
    return produto, midia


def _dados(id_, src, alt="Mesa"):
    return {"images": [{"id": id_, "src": src, "alt": alt, "variantIds": []}]}


def _importar(produto, dados):
    with patch("urllib.request.urlopen", return_value=RespostaImagem(PNG)) as baixar:
        sincronizar_imagens(produto, dados)
    return baixar


def _vinculo(midia):
    return ExternalReference.objects.get(entity_type="midias", object_id=str(midia.pk))


@pytest.mark.django_db
def test_eco_com_a_url_da_cdn_casa_pelo_id_do_vinculo(conta, settings, tmp_path):
    """O webhook traz em admin_graphql_api_id a MediaImage que o envio vinculou."""
    settings.MEDIA_ROOT = tmp_path
    produto, midia = _produto_com_foto_enviada()

    baixar = _importar(produto, _dados("gid://shopify/MediaImage/555", CDN))

    assert baixar.call_count == 0
    assert list(produto.midias.values_list("url", flat=True)) == [HUB]
    assert _vinculo(midia).metadata == {"enviado_src": HUB, "shopify_src": CDN}


@pytest.mark.django_db
def test_eco_repetido_continua_sem_baixar(conta, settings, tmp_path):
    """Depois do primeiro eco a CDN fica no vinculo: o segundo webhook nao baixa."""
    settings.MEDIA_ROOT = tmp_path
    produto, _ = _produto_com_foto_enviada()
    _importar(produto, _dados("gid://shopify/MediaImage/555", CDN))

    baixar = _importar(produto, _dados("gid://shopify/MediaImage/555", CDN))

    assert baixar.call_count == 0
    assert produto.midias.count() == 1


@pytest.mark.django_db
def test_url_de_origem_igual_a_enviada_e_a_mesma_midia(conta, settings, tmp_path):
    """Quando a loja devolve a propria URL do hub, nao ha o que baixar."""
    settings.MEDIA_ROOT = tmp_path
    produto, _ = _produto_com_foto_enviada()

    baixar = _importar(produto, _dados("gid://shopify/ProductImage/9", HUB))

    assert baixar.call_count == 0
    assert produto.midias.count() == 1


class ShopifyFalso:
    """Responde a consulta das midias por id (nodes) e guarda os ids pedidos."""

    def __init__(self, nodes):
        self.nodes, self.pedidos = nodes, []

    def __call__(self, _configuracao):
        return self

    def graphql(self, query, variables=None):
        assert "nodes(ids" in query
        self.pedidos.append(variables["ids"])
        return {"nodes": self.nodes}


def _importar_com_loja(produto, dados, nodes):
    from apps.shopify.contexto import usando_configuracao

    falso = ShopifyFalso(nodes)
    with patch("apps.shopify.midias.ShopifyClient", falso), usando_configuracao(object()):
        baixar = _importar(produto, dados)
    return baixar, falso


@pytest.mark.django_db
def test_foto_enviada_que_falhou_nao_adota_foto_nova_de_mesmo_alt(conta, settings, tmp_path):
    """A foto do hub falhou na loja; a cadastrada la (mesmo alt) tem que chegar ao hub."""
    settings.MEDIA_ROOT = tmp_path
    produto, midia = _produto_com_foto_enviada()
    nova = "https://cdn.shopify.com/s/files/1/outra.png?v=1"

    baixar, falso = _importar_com_loja(
        produto, _dados("gid://shopify/MediaImage/777", nova),
        [{"id": "gid://shopify/MediaImage/555", "status": "FAILED", "image": None}],
    )

    assert falso.pedidos == [["gid://shopify/MediaImage/555"]]
    assert baixar.call_count == 1
    assert produto.midias.count() == 2
    assert "shopify_src" not in _vinculo(midia).metadata


@pytest.mark.django_db
def test_midia_ainda_processando_no_envio_casa_pela_consulta(conta, settings, tmp_path):
    """Sem a CDN gravada no envio, o eco com outro id casa perguntando a loja pela midia."""
    settings.MEDIA_ROOT = tmp_path
    produto, midia = _produto_com_foto_enviada()

    baixar, _ = _importar_com_loja(
        produto, _dados("gid://shopify/ProductImage/42", CDN),
        [{"id": "gid://shopify/MediaImage/555", "status": "READY",
          "image": {"url": CDN.replace("?v=1", "?v=2")}}],
    )

    assert baixar.call_count == 0
    assert produto.midias.count() == 1
    assert _vinculo(midia).metadata["shopify_src"] == CDN


@pytest.mark.django_db
def test_id_de_outro_tipo_com_o_mesmo_numero_nao_e_a_mesma_midia(conta, settings, tmp_path):
    """ProductImage e MediaImage tem numeracoes diferentes: casar pelo numero adotava
    uma foto qualquer da loja no lugar da enviada."""
    settings.MEDIA_ROOT = tmp_path
    produto, _ = _produto_com_foto_enviada()
    outra = "https://cdn.shopify.com/s/files/1/outra.png?v=1"

    baixar, _ = _importar_com_loja(
        produto, _dados("gid://shopify/ProductImage/555", outra),
        [{"id": "gid://shopify/MediaImage/555", "status": "PROCESSING", "image": None}],
    )

    assert baixar.call_count == 1


@pytest.mark.django_db
def test_imagem_cadastrada_no_shopify_baixa_uma_vez_e_vincula(conta, settings, tmp_path):
    """Foto nova da loja entra no hub uma vez; o vinculo guarda a CDN, nao a midia do hub."""
    settings.MEDIA_ROOT = tmp_path
    produto, _ = _produto_com_foto_enviada()
    produto.midias.all().delete()
    outra = "https://cdn.shopify.com/s/files/1/lado.png?v=1"

    primeira = _importar(produto, _dados("gid://shopify/ProductImage/7", outra, alt="Lado"))
    segunda = _importar(produto, _dados("gid://shopify/ProductImage/7", outra, alt="Lado"))

    assert primeira.call_count == 1 and segunda.call_count == 0
    midia = produto.midias.get()
    assert midia.url.startswith("/media/produtos/")
    assert not midia.metadados
    vinculo = _vinculo(midia)
    assert vinculo.external_id == "gid://shopify/ProductImage/7"
    assert vinculo.metadata == {"shopify_src": outra}
