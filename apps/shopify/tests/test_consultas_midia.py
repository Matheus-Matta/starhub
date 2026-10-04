"""Consultas de produto leem `media` (MediaImage), nao `images` (deprecado na 2026-07).

Com `images` o vinculo da foto ficava com o id da Image, que nao e o id da
MediaImage que o envio grava e que o webhook traz: o eco nao casava pelo id.
"""

from unittest.mock import patch

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Produto
from apps.shopify.consultas import CONSULTAS
from apps.shopify.imagens import sincronizar_imagens
from apps.shopify.pedidos_produtos import CONSULTA_PRODUTO
from apps.shopify.tests.custo_graphql import custo
from apps.shopify.tests.test_imagens_webhook import PNG, RespostaImagem

CDN = "https://cdn.shopify.com/s/files/1/sofa.png?v=1"
MIDIA = "gid://shopify/MediaImage/321"


def test_consultas_de_produto_nao_usam_images_deprecado():
    for query in (CONSULTAS["produtos"][1], CONSULTA_PRODUTO):
        assert "images(" not in query
        assert "media(first:" in query and "... on MediaImage" in query


def test_sincronizacao_de_produtos_cabe_no_limite_de_custo():
    """Acima de 1000 pontos o Shopify recusa a consulta e a sincronizacao inteira cai."""
    assert custo(CONSULTAS["produtos"][1]) <= 1000


def _node(status="READY", url=CDN):
    return {"id": "gid://shopify/Product/9", "media": {"nodes": [
        {"id": MIDIA, "alt": "Sofa", "status": status,
         "image": {"url": url, "altText": "Sofa"} if url else None},
        {"id": "gid://shopify/Video/5", "alt": "", "status": "READY"},
    ]}}


def _importar(produto, dados):
    with patch("urllib.request.urlopen", return_value=RespostaImagem(PNG)) as baixar:
        sincronizar_imagens(produto, dados)
    return baixar


@pytest.mark.django_db
def test_media_da_consulta_vincula_pelo_id_da_media_image(conta, settings, tmp_path):
    """Video ou foto sem URL ficam de fora; a foto vira midia com vinculo da MediaImage."""
    settings.MEDIA_ROOT = tmp_path
    produto = Produto.objects.create(nome="Sofa")

    baixar = _importar(produto, _node())

    assert baixar.call_count == 1
    midia = produto.midias.get()
    assert midia.alt_text == "Sofa"
    vinculo = ExternalReference.objects.get(entity_type="midias")
    assert (vinculo.external_id, vinculo.object_id) == (MIDIA, str(midia.pk))


@pytest.mark.django_db
def test_webhook_depois_da_consulta_casa_pelo_mesmo_id_sem_baixar(conta, settings, tmp_path):
    """O webhook traz a MediaImage em admin_graphql_api_id: a mesma foto nao e baixada de novo."""
    settings.MEDIA_ROOT = tmp_path
    produto = Produto.objects.create(nome="Sofa")
    _importar(produto, _node())

    baixar = _importar(produto, {"images": [
        {"id": MIDIA, "src": CDN.replace("?v=1", "?v=2"), "alt": "Sofa", "variantIds": []}]})

    assert baixar.call_count == 0
    assert produto.midias.count() == 1


@pytest.mark.django_db
def test_midia_ainda_processando_fica_para_a_proxima(conta, settings, tmp_path):
    """Sem URL (PROCESSING) nao ha o que baixar; o webhook seguinte traz a foto pronta."""
    settings.MEDIA_ROOT = tmp_path
    produto = Produto.objects.create(nome="Sofa")

    baixar = _importar(produto, _node(status="PROCESSING", url=None))

    assert baixar.call_count == 0
    assert not produto.midias.exists()
