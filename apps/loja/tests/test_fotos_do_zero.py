"""Sincronizar > Importar de Suri e WooCommerce refaz as fotos; pedido e webhook nao."""

from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.loja.models import MidiaProduto, Produto
from apps.shopify.recursos import produto as shopify_produto
from apps.suri import sincronizar as suri_sincronizar
from apps.suri.importar_catalogo import importar_produto as importar_suri
from apps.suri.tests.loja_falsa import produto as produto_suri
from apps.woocommerce import sincronizar as woo_sincronizar
from apps.woocommerce.importar_produtos import importar_produto as importar_woo
from apps.woocommerce.tests import exemplos

pytestmark = pytest.mark.django_db
FOTO = "https://loja.test/frente.png"
LOGO = "https://hub.test/static/starhub/img/logo-600.png"


def baixar(url, **_):
    nome = url.rsplit("/", 1)[1]
    return default_storage.url(default_storage.save(f"produtos/{nome}",
                                                    ContentFile(url.encode())))


@pytest.fixture(autouse=True)
def rede(conta, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    with patch("apps.suri.imagens.baixar", side_effect=baixar), \
            patch("apps.woocommerce.imagens.baixar", side_effect=baixar):
        yield


def _com_foto_do_hub(produto):
    """Na segunda variacao: a importacao normal so mexe na padrao."""
    variante = produto.variantes.order_by("-posicao", "-pk").first()
    return MidiaProduto.objects.create(produto=produto, variante=variante, url="/media/hub.png")


def _urls(produto):
    return sorted(produto.midias.values_list("url", flat=True))


def test_suri_refaz_e_a_foto_da_dimensao_vai_para_a_variacao():
    dados = produto_suri(images=[{"url": FOTO}, {"url": LOGO}])
    dados["dimensions"][1]["image"] = {"url": "https://loja.test/verde.png"}
    obj, _ = importar_suri(dados, sobrescrever=True, refazer_fotos=True)
    _com_foto_do_hub(obj)

    importar_suri(dados, sobrescrever=True, refazer_fotos=True)

    assert _urls(obj) == ["/media/produtos/frente.png", "/media/produtos/verde.png"], \
        "sem a do hub e sem a foto padrao que o hub manda no lugar da vazia"
    verde = obj.variantes.get(sku="CAM-VD")
    assert [m.url for m in verde.midias.all()] == ["/media/produtos/verde.png"]


def test_woo_refaz_as_fotos():
    dados = exemplos.produto_simples(images=[{"id": 31, "src": FOTO, "alt": ""}])
    obj, _ = importar_woo(dados, sobrescrever=True)
    MidiaProduto.objects.create(produto=obj, url="/media/hub.png")

    importar_woo(dados, sobrescrever=True, refazer_fotos=True)

    assert _urls(obj) == ["/media/produtos/frente.png"]


@pytest.mark.parametrize("importar, dados", [
    (importar_suri, produto_suri(images=[{"url": FOTO}])),
    (importar_woo, exemplos.produto_simples(images=[{"id": 31, "src": FOTO, "alt": ""}])),
])
def test_importacao_pelo_pedido_nao_apaga_fotos_do_hub(importar, dados):
    """O pedido usa o mesmo importador com `sobrescrever`: cada venda apagaria fotos."""
    obj, _ = importar(dados)
    MidiaProduto.objects.create(produto=obj, url="/media/hub.png")
    importar(dados, sobrescrever=True)
    assert "/media/hub.png" in _urls(Produto.objects.get(pk=obj.pk))


def test_sincronizar_woo_pede_para_refazer():
    with patch("apps.woocommerce.sincronizar.importar_completo") as importar:
        woo_sincronizar.importadores(None, None, {})["produtos"]({})
    assert importar.call_args.kwargs["refazer_fotos"] is True


def test_sincronizar_suri_pede_para_refazer():
    modulo = "apps.suri.sincronizar."
    with (patch(modulo + "SuriClient") as cliente,
          patch(modulo + "recursos_para_buscar", return_value=["produtos"]),
          patch(modulo + "importar_produto", return_value=(None, False)) as importar):
        cliente.return_value.produtos.return_value = [{"id": "1"}]
        suri_sincronizar.sincronizar_loja(None, lambda *_: None)
    assert importar.call_args.kwargs["refazer_fotos"] is True


def test_sincronizar_shopify_refaz_e_o_webhook_nao():
    dados = {"id": "gid://shopify/Product/9", "title": "Mesa", "handle": "mesa",
             "variants": {"nodes": [{"id": "gid://shopify/ProductVariant/1", "sku": "M1"}]}}
    with patch("apps.shopify.recursos.imagens_refazer.refazer") as refazer:
        shopify_produto(dados)
        assert not refazer.called
        shopify_produto(dados, sobrescrever=True)
    assert refazer.called
