"""Imagens do produto no envio ao Shopify: sempre vao, mas a mesma URL nunca vai duas vezes.

O vinculo da midia (ExternalReference "midias") guarda a URL do hub enviada; sem ele,
cada edicao do produto no hub mandaria a galeria inteira de novo e a loja ficaria
com a mesma foto repetida.
"""

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import MidiaProduto
from apps.shopify.tests.test_envio_produtos import PRODUTO_GID, _enviador, _simples

HUB = "https://hub.exemplo.com/media/produtos/mesa.png"
CDN = "https://cdn.shopify.com/s/files/1/mesa.png?v=1"
LOCAL = {"id": "gid://shopify/Location/1"}
PROCESSANDO = {"nodes(ids": {"nodes": [
    {"id": "gid://shopify/MediaImage/77", "status": "PROCESSING", "image": None}]}}


def _midias(*ids):
    return {"nodes": [{"id": f"gid://shopify/MediaImage/{n}"} for n in ids]}


def _set(*midias):
    return {"productSet": {"product": {
        "id": PRODUTO_GID, "media": _midias(*midias),
        "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/1", "position": 1,
                                "inventoryItem": {"id": "gid://shopify/InventoryItem/1"}}]},
    }, "userErrors": []}}


def _update(*midias):
    return {"productUpdate": {"product": {"id": PRODUTO_GID, "media": _midias(*midias)},
                              "userErrors": []}}


def _respostas_update(*midias):
    return {
        "productVariantsBulkUpdate": {"productVariantsBulkUpdate": {
            "productVariants": [], "userErrors": []}},
        "productUpdate": _update(*midias), "location": {"location": LOCAL}, **PROCESSANDO,
    }


def _vincular_variante(variante):
    ExternalReference.objects.create(
        platform="shopify", entity_type="variantes", object_id=str(variante.pk),
        external_id="gid://shopify/ProductVariant/1", external_parent_id=PRODUTO_GID,
    )


def _chamada(enviador, raiz):
    return next(v for q, v in enviador.cliente.chamadas if raiz in q)


def _vinculo(midia):
    return ExternalReference.objects.get(entity_type="midias", object_id=str(midia.pk))


@pytest.mark.django_db
def test_produto_novo_manda_as_imagens_no_product_set_e_vincula_a_midia(conta):
    """Produto criado no hub chegava na loja sem nenhuma foto."""
    produto, _ = _simples()
    midia = MidiaProduto.objects.create(produto=produto, url=HUB, alt_text="Mesa de frente")
    enviador = _enviador(conta, {"location": {"location": LOCAL}, "productSet": _set(77),
                                 "nodes(ids": {"nodes": [{"id": "gid://shopify/MediaImage/77",
                                                          "status": "READY",
                                                          "image": {"url": CDN}}]}})

    enviador.criar(produto)

    entrada = _chamada(enviador, "productSet")["input"]
    assert entrada["files"] == [
        {"originalSource": HUB, "alt": "Mesa de frente", "contentType": "IMAGE"}
    ]
    vinculo = _vinculo(midia)
    assert vinculo.external_id == "gid://shopify/MediaImage/77"
    # A CDN ja fica no vinculo: o webhook de volta casa sem consultar a loja.
    assert _chamada(enviador, "nodes(ids") == {"ids": ["gid://shopify/MediaImage/77"]}
    assert vinculo.metadata == {"enviado_src": HUB, "shopify_src": CDN}
    midia.refresh_from_db()
    assert not midia.metadados, "dado do Shopify nao vai no registro do hub"


@pytest.mark.django_db
def test_update_manda_so_a_imagem_que_ainda_nao_esta_no_shopify(conta):
    """Reenviar a galeria toda a cada edicao duplicava as fotos na loja."""
    produto, variante = _simples()
    _vincular_variante(variante)
    antiga = MidiaProduto.objects.create(produto=produto, url=HUB, posicao=0)
    ExternalReference.objects.create(
        platform="shopify", entity_type="midias", object_id=str(antiga.pk),
        external_id="gid://shopify/MediaImage/77", metadata={"enviado_src": HUB},
    )
    nova = MidiaProduto.objects.create(
        produto=produto, url="https://hub.exemplo.com/media/produtos/lado.png", posicao=1
    )
    enviador = _enviador(conta, _respostas_update(77, 78))

    enviador.atualizar(produto, PRODUTO_GID)

    entrada = _chamada(enviador, "productUpdate")
    assert entrada["media"] == [{
        "originalSource": "https://hub.exemplo.com/media/produtos/lado.png", "alt": "",
        "mediaContentType": "IMAGE",
    }]
    vinculo = _vinculo(nova)
    assert vinculo.external_id == "gid://shopify/MediaImage/78"
    assert vinculo.metadata == {"enviado_src": "https://hub.exemplo.com/media/produtos/lado.png"}


@pytest.mark.django_db
def test_mesma_url_ja_enviada_nao_vai_de_novo(conta):
    """A mesma foto ligada a outra variante (outra linha no hub) ja esta na loja."""
    produto, variante = _simples()
    _vincular_variante(variante)
    primeira = MidiaProduto.objects.create(produto=produto, url=HUB)
    ExternalReference.objects.create(
        platform="shopify", entity_type="midias", object_id=str(primeira.pk),
        external_id="gid://shopify/MediaImage/77", metadata={"enviado_src": HUB},
    )
    MidiaProduto.objects.create(produto=produto, variante=variante, url=HUB)
    enviador = _enviador(conta, _respostas_update(77))

    enviador.atualizar(produto, PRODUTO_GID)

    assert "media" not in _chamada(enviador, "productUpdate")


@pytest.mark.django_db
def test_imagem_que_veio_do_shopify_nao_volta_para_la(conta):
    """Midia importada (vinculo com shopify_src) ja e da loja: reenviar criaria copia."""
    produto, variante = _simples()
    _vincular_variante(variante)
    importada = MidiaProduto.objects.create(produto=produto, url="/media/produtos/x.png")
    ExternalReference.objects.create(
        platform="shopify", entity_type="midias", object_id=str(importada.pk),
        external_id="gid://shopify/ProductImage/5",
        metadata={"shopify_src": "https://cdn.shopify.com/x.png"},
    )
    enviador = _enviador(conta, _respostas_update(5))

    enviador.atualizar(produto, PRODUTO_GID)

    assert "media" not in _chamada(enviador, "productUpdate")


@pytest.mark.django_db
def test_url_relativa_do_media_vira_absoluta_pela_url_publica_do_hub(conta):
    """O Shopify baixa a imagem pela URL: "/media/..." sozinho ele nao consegue abrir."""
    produto, _ = _simples()
    MidiaProduto.objects.create(produto=produto, url="/media/produtos/mesa.png")
    enviador = _enviador(conta, {"location": {"location": LOCAL}, "productSet": _set(77),
                                 **PROCESSANDO})
    enviador.configuracao.url_webhook = "https://hub.exemplo.com/integracoes/shopify/webhook"

    enviador.criar(produto)

    [arquivo] = _chamada(enviador, "productSet")["input"]["files"]
    assert arquivo["originalSource"] == HUB


@pytest.mark.django_db
def test_url_relativa_sem_url_publica_nao_e_enviada(conta):
    """Sem endereco publico o Shopify falharia a midia em silencio e nunca tentaria de novo."""
    produto, _ = _simples()
    MidiaProduto.objects.create(produto=produto, url="/media/produtos/mesa.png")
    enviador = _enviador(conta, {"location": {"location": LOCAL}, "productSet": _set()})

    enviador.criar(produto)

    assert "files" not in _chamada(enviador, "productSet")["input"]
    assert not ExternalReference.objects.filter(entity_type="midias").exists()
