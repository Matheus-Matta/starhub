"""Baixa a imagem de uma URL que veio de fora (loja, marketplace) para o MEDIA do hub.

    src = baixar("https://loja.com/foto.jpg")   # "/media/produtos/2026/10/foto.jpg"

So http(s) publico: a URL vem de outro sistema, e um endereco interno (localhost,
rede privada) faria o hub buscar dentro da propria rede. Ate 5 MB; o tipo e
conferido pelo conteudo (apps.core.imagens.salvar), nao pela extensao.
"""

import ipaddress
import socket
import urllib.request
from pathlib import PurePath
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from apps.core.imagens import TAMANHO_MAXIMO, salvar


class ImagemErro(RuntimeError):
    pass


def _publico(host):
    try:
        enderecos = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror as erro:
        raise ImagemErro(f"host {host} nao encontrado") from erro
    return all(ipaddress.ip_address(e).is_global for e in enderecos)


def _sem_espacos(partes):
    # URL de blob com espaco no caminho ("Produto teste/image-0.jpeg") e recusada
    # pelo urllib; o caminho vai codificado, o resto fica como veio.
    return urlunsplit(partes._replace(path=quote(unquote(partes.path), safe="/%")))


def baixar(url, pasta="produtos", timeout=20):
    partes = urlsplit((url or "").strip())
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise ImagemErro("a imagem nao e um endereco http(s).")
    if not _publico(partes.hostname):
        raise ImagemErro(f"{partes.hostname} nao e um endereco publico.")
    nome = PurePath(unquote(partes.path)).name or "imagem"
    requisicao = urllib.request.Request(_sem_espacos(partes),
                                        headers={"User-Agent": "StarHub/1.0"})
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            conteudo = resposta.read(TAMANHO_MAXIMO + 1)
    except (HTTPError, URLError, TimeoutError, ValueError) as erro:
        raise ImagemErro(f"nao foi possivel baixar {nome}: {erro}") from erro
    if len(conteudo) > TAMANHO_MAXIMO:
        raise ImagemErro(f"{nome} passa de 5 MB; reduza a foto na origem.")
    try:
        return salvar(ContentFile(conteudo, name=nome), pasta)["src"]
    except ValidationError as erro:
        raise ImagemErro(f"{nome}: {erro.messages[0]}") from erro
