"""Imagens da variante: a galeria do form vira linhas de MidiaProduto ligadas a ela.

A ordem da galeria e a ordem gravada (posicao 0, 1, 2...). A primeira imagem da
variante padrao e a capa do produto (Produto.imagens, listagem e API Woo).

    sincronizar_midias(variante, [{"id": 7, "src": "/media/produtos/a.png", "alt": ""},
                                  {"src": "https://cdn.test/b.jpg", "alt": "Verso"}])
    -> a midia 7 fica em 1o, "b.jpg" nasce em 2o, as outras da variante somem.
"""

from apps.loja.models import MidiaProduto


def imagens_da_variante(variante):
    """Formato do widget de imagens: [{"id", "src", "alt"}] na ordem gravada."""
    if variante.pk is None:
        return []
    return [
        {"id": midia.pk, "src": midia.url, "alt": midia.alt_text}
        for midia in variante.midias.order_by("posicao", "id")
    ]


def sincronizar_midias(variante, imagens):
    existentes = {midia.pk: midia for midia in variante.midias.all()}
    for posicao, item in enumerate(imagens or []):
        midia = existentes.pop(item.get("id"), None) or MidiaProduto(
            produto_id=variante.produto_id, variante=variante
        )
        midia.url = item["src"]
        midia.alt_text = (item.get("alt") or "")[:255]
        midia.posicao = posicao
        midia.save()
    for sobra in existentes.values():
        sobra.delete()
