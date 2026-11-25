"""Reconhece a mesma imagem guardada em dois arquivos do MEDIA.

O nome nao serve: cada download ganha um uuid novo, e a mesma foto baixada tres vezes
vira tres nomes. Vale o conteudo (sha256).

    identidade("/media/produtos/a.png") == identidade("/media/produtos/copia.png")

URL de fora do hub (ou arquivo que sumiu) so e igual a ela mesma.
"""

import hashlib
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.core.files.storage import default_storage


def nome_no_media(url):
    """`produtos/a.png` de `/media/produtos/a.png` ou `https://hub/media/produtos/a.png`
    (o ERP devolve a URL inteira); vazio quando o arquivo nao e do MEDIA do hub."""
    caminho = unquote(urlsplit(url or "").path)
    prefixo = "/" + settings.MEDIA_URL.strip("/") + "/"
    if not caminho.startswith(prefixo) or ".." in caminho.split("/"):
        return ""
    nome = caminho.removeprefix(prefixo)
    return nome if nome and default_storage.exists(nome) else ""


def mesmo_arquivo(url):
    """Chave do endereco: a relativa e a absoluta do mesmo arquivo dao a mesma."""
    return nome_no_media(url) or url


def identidade(url):
    nome = nome_no_media(url)
    if not nome:
        return url
    with default_storage.open(nome, "rb") as arquivo:
        return "sha256:" + hashlib.sha256(arquivo.read()).hexdigest()


def url_ja_guardada(nova, existentes):
    """URL das `existentes` com a mesma imagem da `nova`, ou None. O tamanho do arquivo
    decide antes do hash: quase sempre descarta sem ler a foto inteira."""
    nome = nome_no_media(nova)
    if not nome:
        return None
    tamanho, alvo = default_storage.size(nome), identidade(nova)
    for url in existentes:
        outro = nome_no_media(url)
        if outro and default_storage.size(outro) == tamanho and identidade(url) == alvo:
            return url
    return None
