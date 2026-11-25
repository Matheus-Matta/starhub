"""Importacao do Shopify que nao acumula copias da mesma foto."""

from unittest.mock import patch

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import MidiaProduto, VarianteProduto
from apps.loja.services.variantes import criar_produto
from apps.shopify.imagens import sincronizar_imagens
from apps.shopify.tests.test_imagens_webhook import PNG, RespostaImagem

CDN = "https://cdn.shopify.com/s/files/1/mesa.png?v=1"


@pytest.fixture(autouse=True)
def media(conta, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def importar(produto, imagens):
    with patch("urllib.request.urlopen", side_effect=lambda *a, **k: RespostaImagem(PNG)):
        sincronizar_imagens(produto, {"images": imagens})


@pytest.mark.django_db
def test_webhook_simultaneo_nao_grava_a_foto_que_o_outro_acabou_de_gravar():
    """O segundo webhook leu os vinculos antes do primeiro gravar: baixa a mesma foto,
    mas ao gravar encontra a que ja entrou."""
    produto = criar_produto("Mesa", sku="M1")
    imagem = [{"id": "gid://shopify/MediaImage/1", "src": CDN}]
    importar(produto, imagem)

    with patch("apps.shopify.imagens.vinculos.do_produto", return_value=[]):
        importar(produto, imagem)

    assert produto.midias.count() == 1


@pytest.mark.django_db
def test_foto_da_variante_sem_variant_ids_nao_ganha_copia_na_padrao():
    """A consulta GraphQL nao diz a variante: cada sincronizacao copiava a foto da cor
    para a variante padrao."""
    produto = criar_produto("Mesa", sku="M1")
    azul = VarianteProduto.objects.create(produto=produto, titulo="Azul", posicao=1)
    midia = MidiaProduto.objects.create(produto=produto, variante=azul, url="/media/azul.png")
    ExternalReference.objects.create(
        platform="shopify", entity_type="midias", object_id=str(midia.pk),
        external_id="gid://shopify/MediaImage/1", metadata={"shopify_src": CDN})

    importar(produto, [{"id": "gid://shopify/MediaImage/1", "src": CDN}])

    assert produto.midias.get().variante == azul


@pytest.mark.django_db
def test_repetida_na_loja_nao_muda_a_posicao_da_capa():
    """Duas midias da loja apontam para a mesma linha (repetidas juntadas): a segunda
    levava a capa para o fim da galeria."""
    produto = criar_produto("Mesa", sku="M1")
    importar(produto, [{"id": f"gid://shopify/MediaImage/{n}",
                        "src": CDN.replace("mesa", f"mesa{n}")} for n in (1, 2, 3)])

    assert produto.midias.get().posicao == 0
    assert ExternalReference.objects.filter(entity_type="midias").count() == 3
