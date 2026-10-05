"""Imagens do produto do hub -> `images` do produto no WooCommerce.

O Woo troca a galeria inteira pela lista enviada: imagem ja na loja vai pelo id
(nao baixa de novo), imagem nova vai pela URL publica do hub. A resposta devolve as
imagens na mesma ordem, e cada nova ganha o vinculo "midias" com o id de la.
"""

from apps.integracoes.url_publica import url_publica
from apps.loja.models import MidiaProduto
from apps.woocommerce import vinculos


def _midias(produto):
    vistas, saida = set(), []
    for midia in produto.midias.filter(tipo=MidiaProduto.Tipo.IMAGEM).order_by("posicao", "id"):
        if midia.url not in vistas:  # a mesma foto em duas variantes e uma imagem so
            vistas.add(midia.url)
            saida.append(midia)
    return saida


def imagens(configuracao, produto):
    """([{"id"} ou {"src", "alt"}], [midia de cada item]); imagem sem URL publica fica fora."""
    lista, midias = [], []
    for midia in _midias(produto):
        woo_id = vinculos.externo_id("midias", midia.pk)
        if woo_id:
            lista.append({"id": int(woo_id)})
        else:
            src = url_publica(configuracao, midia.url)
            if not src:
                continue
            lista.append({"src": src, "alt": midia.alt_text})
        midias.append(midia)
    return lista, midias


def vincular(midias, resposta):
    for midia, imagem in zip(midias, resposta.get("images") or [], strict=False):
        if imagem.get("id"):
            vinculos.referenciar("midias", imagem["id"], midia,
                                 metadata={"src": imagem.get("src") or ""})
