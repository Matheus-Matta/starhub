"""Imagens da variante: a galeria do form vira linhas de MidiaProduto ligadas a ela.

A ordem da galeria e a ordem gravada (posicao 0, 1, 2...). A primeira imagem da
variante padrao e a capa do produto (Produto.imagens, listagem e API Woo).

    sincronizar_midias(variante, [{"id": 7, "src": "/media/produtos/a.png", "alt": ""},
                                  {"src": "https://cdn.test/b.jpg", "alt": "Verso"}])
    -> a midia 7 fica em 1o, "b.jpg" nasce em 2o, as outras da variante somem.

MidiaProduto nao gera envio sozinha (nao esta no MAPA do distribuidor): se a galeria
mudou, o produto vai aos marketplaces como update. Sem isso, apagar 4 de 6 fotos sem
mexer em outro campo deixava Shopify e Suri com as 6.
"""

from apps.core.imagens_iguais import mesmo_arquivo, url_ja_guardada
from apps.loja.models import MidiaProduto


def imagens_da_variante(variante):
    """Formato do widget de imagens: [{"id", "src", "alt"}] na ordem gravada."""
    if variante.pk is None:
        return []
    return [
        {"id": midia.pk, "src": midia.url, "alt": midia.alt_text}
        for midia in variante.midias.order_by("posicao", "id")
    ]


def _retrato(variante):
    return list(variante.midias.order_by("posicao", "id").values_list(
        "pk", "url", "alt_text", "posicao"))


def _casar(existentes, imagens):
    """[(item, midia existente ou None)] sem foto repetida; tira de `existentes` as usadas.

    Casa pelo id e, sem ele, pelo arquivo: quem manda so o `src` (ERP, importacao) recriava
    a linha a cada envio, e a nova, sem vinculo, subia outra copia para as lojas."""
    unicos = {}
    for item in imagens or []:
        unicos.setdefault(mesmo_arquivo(item["src"]), item)
    pares = {chave: existentes.pop(item.get("id"), None) for chave, item in unicos.items()}
    por_arquivo = {mesmo_arquivo(m.url): m for m in reversed(list(existentes.values()))}
    for chave, midia in pares.items():
        if midia is None and chave in por_arquivo:
            pares[chave] = existentes.pop(por_arquivo[chave].pk)
    return [(item, pares[chave]) for chave, item in unicos.items()]


def sincronizar_midias(variante, imagens):
    antes = _retrato(variante)
    existentes = {midia.pk: midia for midia in variante.midias.all()}
    for posicao, (item, midia) in enumerate(_casar(existentes, imagens)):
        # O ERP devolve a URL inteira do mesmo arquivo: e a mesma foto, sem mexer na url.
        if midia and mesmo_arquivo(midia.url) != mesmo_arquivo(item["src"]):
            # Outra foto no lugar: linha nova. A antiga sai com o vinculo dela e as lojas
            # apagam uma e recebem a outra; na mesma linha, a nova passaria pela antiga.
            existentes[midia.pk] = midia
            midia = None
        midia = midia or MidiaProduto(produto_id=variante.produto_id, variante=variante,
                                      url=item["src"])
        midia.alt_text = (item.get("alt") or "")[:255]
        midia.posicao = posicao
        midia.save()
    for sobra in existentes.values():
        sobra.delete()
    if _retrato(variante) != antes:
        from apps.integracoes.envio.distribuidor import obter

        obter().filhos_do_produto(variante.produto)


def url_da_foto(produto, url, lista=()):
    """Foto recem-baixada: a URL da igual que o produto (ou a `lista` em montagem) ja tem."""
    atuais = [*produto.midias.values_list("url", flat=True), *(i["src"] for i in lista)]
    return url_ja_guardada(url, atuais) or url
