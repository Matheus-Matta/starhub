"""Upload de imagem dos widgets do tema (produto, categoria).

Sem Pillow: a imagem e conferida pela ASSINATURA do arquivo (os primeiros
bytes), nao pela extensao nem pelo Content-Type, que o navegador deixa o
usuario mandar errado. Exemplo: um .exe renomeado para foto.jpg e recusado.
"""

import uuid
from pathlib import PurePath

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage

TAMANHO_MAXIMO = 5 * 1024 * 1024  # 5 MB por imagem
ASSINATURAS = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".webp": (b"RIFF",),  # + "WEBP" no byte 8, conferido abaixo
}


def tipo_da_imagem(arquivo):
    cabeca = arquivo.read(16)
    arquivo.seek(0)
    for extensao, assinaturas in ASSINATURAS.items():
        if any(cabeca.startswith(a) for a in assinaturas):
            if extensao == ".webp" and cabeca[8:12] != b"WEBP":
                continue
            return extensao
    return None


def validar(arquivo):
    if arquivo.size > TAMANHO_MAXIMO:
        raise ValidationError(f"{arquivo.name}: passa de 5 MB. Reduza a imagem e envie de novo.")
    extensao = tipo_da_imagem(arquivo)
    if extensao is None:
        raise ValidationError(f"{arquivo.name}: nao e uma imagem PNG, JPG, GIF ou WEBP.")
    return extensao


def salvar(arquivo, pasta):
    """Grava no MEDIA e devolve o item no formato de imagem do Woo."""
    extensao = validar(arquivo)
    caminho = default_storage.save(f"{pasta}/{uuid.uuid4().hex}{extensao}", arquivo)
    return {"src": default_storage.url(caminho), "name": PurePath(arquivo.name).stem, "alt": ""}
