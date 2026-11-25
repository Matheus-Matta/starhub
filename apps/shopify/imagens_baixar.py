"""Baixa a foto da CDN da Shopify para o MEDIA, reduzida quando passa de 5 MB."""

import urllib.request
from pathlib import PurePath
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from django.core.files.base import ContentFile

from apps.core.imagens import TAMANHO_MAXIMO, salvar

HOSTS_SHOPIFY = {"cdn.shopify.com", "cdn.shopifycdn.net"}


class ImagemShopifyErro(RuntimeError):
    pass


# Foto maior que 5 MB (PNG de ambiente da loja) vem reduzida pela propria CDN da
# Shopify (`width=`): 2048 px sobra para a vitrine e cabe no limite do hub.
LARGURAS = (2048, 1600, 1200)


def _com_largura(url, largura):
    partes = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(partes.query) if k != "width"] + [("width", largura)]
    return urlunsplit(partes._replace(query=urlencode(query)))


def _ler(url, nome, timeout):
    """Bytes da imagem, ou None se passa de 5 MB."""
    requisicao = urllib.request.Request(url, headers={"User-Agent": "StarHub/1.0"})
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            if int(resposta.headers.get("Content-Length") or 0) > TAMANHO_MAXIMO:
                return None
            conteudo = resposta.read(TAMANHO_MAXIMO + 1)
    except (HTTPError, URLError, TimeoutError, ValueError) as erro:
        raise ImagemShopifyErro(f"Nao foi possivel baixar {nome}: {erro}") from erro
    return conteudo if len(conteudo) <= TAMANHO_MAXIMO else None


def _baixar(url, timeout=20, pasta="produtos"):
    partes = urlsplit(url)
    if partes.scheme != "https" or partes.hostname not in HOSTS_SHOPIFY:
        raise ImagemShopifyErro("A imagem nao pertence ao CDN HTTPS da Shopify.")
    nome = PurePath(unquote(partes.path)).name or "imagem"
    for tentativa in (url, *(_com_largura(url, largura) for largura in LARGURAS)):
        conteudo = _ler(tentativa, nome, timeout)
        if conteudo is not None:
            item = salvar(ContentFile(conteudo, name=nome), pasta)
            return item["src"]
    raise ImagemShopifyErro(
        f"{nome}: passa de 5 MB mesmo reduzida a {LARGURAS[-1]} px; "
        "diminua a foto na loja e sincronize de novo."
    )
