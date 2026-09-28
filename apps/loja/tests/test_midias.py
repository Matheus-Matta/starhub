"""Imagens moram na variante: a ordem da galeria e a gravada, e a 1a da variante
padrao e a capa do produto (listagem e API Woo)."""

import pytest

from apps.loja.models import MidiaProduto, VarianteProduto
from apps.loja.services.midias import imagens_da_variante, sincronizar_midias
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db


def test_galeria_grava_a_ordem_mantem_por_id_e_remove_o_que_saiu():
    variante = criar_produto("Camiseta", sku="CAM-1").variante_padrao
    sincronizar_midias(variante, [{"src": "https://cdn.test/a.jpg"}, {"src": "https://cdn.test/b.jpg"}])
    a, b = imagens_da_variante(variante)
    sincronizar_midias(variante, [b, {"src": "https://cdn.test/c.jpg", "alt": "Costas"}])
    depois = imagens_da_variante(variante)
    assert [i["src"] for i in depois] == ["https://cdn.test/b.jpg", "https://cdn.test/c.jpg"]
    assert depois[0]["id"] == b["id"]  # arrastou para frente: a mesma midia, nao uma copia
    assert not MidiaProduto.objects.filter(pk=a["id"]).exists()


def test_capa_do_produto_e_a_primeira_imagem_da_variante_padrao():
    produto = criar_produto("Camiseta", sku="CAM-1")
    outra = VarianteProduto.objects.create(produto=produto, titulo="Azul", posicao=1)
    sincronizar_midias(outra, [{"src": "https://cdn.test/azul.jpg"}])
    sincronizar_midias(produto.variante_padrao, [{"src": "https://cdn.test/capa.jpg"}])
    assert [i["src"] for i in produto.imagens] == [
        "https://cdn.test/capa.jpg", "https://cdn.test/azul.jpg",
    ]
