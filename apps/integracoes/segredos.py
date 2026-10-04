"""Criptografia reversivel das credenciais usadas para chamar marketplaces."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def criptografar(valor):
    if not valor:
        return ""
    return _fernet().encrypt(str(valor).encode()).decode()


def descriptografar(valor):
    if not valor:
        return ""
    try:
        return _fernet().decrypt(valor.encode()).decode()
    except (InvalidToken, ValueError):
        return ""
