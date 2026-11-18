"""Trocar so as imagens do produto no hub tem de gerar envio aos marketplaces.

MidiaProduto nao esta no MAPA do distribuidor: apagar 4 das 6 fotos (ou trocar uma)
sem mexer em outro campo nao enviava nada, e Shopify e Suri ficavam com as 6.
"""

import pytest

from apps.loja.models import MidiaProduto, Produto
from apps.loja.services.midias import sincronizar_midias

from .envio_falso import configuracao


def _com_fotos(total):
    produto = Produto.objects.create(nome="Mesa")
    variante = produto.variantes.get()
    sincronizar_midias(variante, [{"src": f"https://hub.test/{n}.png"} for n in range(total)])
    return produto, variante


@pytest.mark.django_db
def test_apagar_imagens_envia_o_produto(falsos, enfileirados,
                                        django_capture_on_commit_callbacks):
    produto, variante = _com_fotos(6)
    configuracao("shopify")
    ficam = [{"id": m.pk, "src": m.url} for m in variante.midias.order_by("posicao")[:2]]

    with django_capture_on_commit_callbacks(execute=True):
        sincronizar_midias(variante, ficam)

    assert MidiaProduto.objects.count() == 2
    assert enfileirados == [("shopify", "produtos", "update", str(produto.pk))]


@pytest.mark.django_db
def test_trocar_a_url_da_imagem_envia_o_produto(falsos, enfileirados,
                                                django_capture_on_commit_callbacks):
    produto, variante = _com_fotos(1)
    configuracao("shopify")
    midia = variante.midias.get()

    with django_capture_on_commit_callbacks(execute=True):
        sincronizar_midias(variante, [{"id": midia.pk, "src": "https://hub.test/nova.png"}])

    assert enfileirados == [("shopify", "produtos", "update", str(produto.pk))]


@pytest.mark.django_db
def test_galeria_igual_nao_envia(falsos, enfileirados, django_capture_on_commit_callbacks):
    _, variante = _com_fotos(2)
    configuracao("shopify")
    iguais = [{"id": m.pk, "src": m.url, "alt": m.alt_text}
              for m in variante.midias.order_by("posicao")]

    with django_capture_on_commit_callbacks(execute=True):
        sincronizar_midias(variante, iguais)

    assert enfileirados == []
