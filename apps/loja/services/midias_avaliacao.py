"""Fotos e video da avaliacao: o que o cliente pode anexar pelo tema.

O video e conferido pela assinatura do arquivo, como as imagens (apps/core/imagens):
MP4/MOV tem "ftyp" no byte 4 e WebM comeca com o cabecalho EBML.
"""

from pathlib import PurePath

from django.core.exceptions import ValidationError

from apps.core import imagens

VIDEO_TAMANHO_MAXIMO = 50 * 1024 * 1024  # 50 MB: o tema avisa antes de enviar
VIDEOS_MAXIMO = 1
EXTENSOES_VIDEO = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}


def tipo_do_video(arquivo):
    cabeca = arquivo.read(16)
    arquivo.seek(0)
    if cabeca[4:8] == b"ftyp":
        return ".mov" if cabeca[8:12] == b"qt  " else ".mp4"
    if cabeca.startswith(b"\x1a\x45\xdf\xa3"):
        return ".webm"
    return None


def validar(arquivo):
    """Extensao do arquivo (".png", ".mp4"...); ValidationError com o que corrigir."""
    extensao = tipo_do_video(arquivo)
    if extensao is None:
        return imagens.validar(arquivo)
    if arquivo.size > VIDEO_TAMANHO_MAXIMO:
        limite = VIDEO_TAMANHO_MAXIMO // (1024 * 1024)
        raise ValidationError(f"O video passa de {limite} MB. Envie um video mais curto.")
    return extensao


def _extensao(nome):
    # Aceita ".mp4" ou "pasta/x.mp4": PurePath(".mp4").suffix e vazio.
    return nome.lower() if nome.startswith(".") else PurePath(nome).suffix.lower()


def e_video(nome):
    return _extensao(nome) in EXTENSOES_VIDEO


def mime_do_video(nome):
    return EXTENSOES_VIDEO[_extensao(nome)]
