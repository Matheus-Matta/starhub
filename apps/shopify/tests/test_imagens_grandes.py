"""Foto grande da loja: baixa a versao reduzida pela CDN e nao derruba o produto."""

from io import BytesIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from apps.core.imagens import TAMANHO_MAXIMO
from apps.loja.models import MidiaProduto, Produto
from apps.shopify.contexto import coletando_avisos
from apps.shopify.imagens import sincronizar_imagens
from apps.shopify.tests.test_imagens_webhook import PNG

pytestmark = pytest.mark.django_db
GRANDE = "https://cdn.shopify.com/s/files/1/ambiente.png?v=7"
PEQUENA = "https://cdn.shopify.com/s/files/1/mesa.png?v=1"


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


class Resposta(BytesIO):
    def __init__(self, conteudo):
        super().__init__(conteudo)
        self.headers = {"Content-Length": str(len(conteudo))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _cdn(pedidos, grande_ate=None):
    """CDN falsa: a foto "ambiente" passa de 5 MB ate pedir largura <= grande_ate."""

    def urlopen(requisicao, timeout=None):
        url = requisicao.full_url
        pedidos.append(url)
        largura = parse_qs(urlsplit(url).query).get("width", [None])[0]
        reduzida = grande_ate is not None and largura and int(largura) <= grande_ate
        if "ambiente" in url and not reduzida:
            return Resposta(PNG + b"\x00" * TAMANHO_MAXIMO)
        return Resposta(PNG)

    return urlopen


def _dados(*fotos):
    return {"images": [{"id": f"gid://shopify/MediaImage/{n}", "src": src, "alt": ""}
                       for n, src in enumerate(fotos, start=1)]}


def test_foto_acima_de_5mb_vem_reduzida_pela_cdn():
    """PNG de ambiente com 8 MB era recusado e o produto ficava sem nenhuma foto."""
    produto = Produto.objects.create(nome="Roupeiro")
    pedidos = []
    with patch("urllib.request.urlopen", _cdn(pedidos, grande_ate=2048)):
        sincronizar_imagens(produto, _dados(GRANDE))
    assert MidiaProduto.objects.filter(produto=produto).count() == 1
    assert "width=2048" in pedidos[-1] and "v=7" in pedidos[-1]


def test_foto_que_nao_baixa_vira_aviso_e_as_outras_entram():
    """Uma foto ruim desfazia o produto inteiro: as boas tambem sumiam."""
    produto = Produto.objects.create(nome="Cozinha")
    with patch("urllib.request.urlopen", _cdn([])), coletando_avisos() as avisos:
        sincronizar_imagens(produto, _dados(GRANDE, PEQUENA))
    assert MidiaProduto.objects.filter(produto=produto).count() == 1
    assert len(avisos) == 1
    assert "ambiente.png" in avisos[0]["motivo"] and avisos[0]["id"] == str(produto.pk)
