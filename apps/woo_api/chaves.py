"""Geracao e conferencia das chaves ck_/cs_ no formato do WooCommerce.

Guardamos so o hash SHA-256 das duas partes. A chave inteira aparece uma unica
vez, na criacao; se vazar o banco, ninguem entra na API com o que esta la.
SHA-256 simples (sem sal) basta porque a chave tem 160 bits aleatorios: nao ha
dicionario de senha fraca para testar.
"""

import hashlib
import hmac
import secrets


def gerar_par():
    chave = f"ck_{secrets.token_hex(20)}"
    segredo = f"cs_{secrets.token_hex(20)}"
    return chave, segredo


def hash_de(valor):
    return hashlib.sha256(valor.encode()).hexdigest()


def segredo_confere(segredo_hash, segredo):
    # compare_digest: tempo constante, nao entrega o segredo por medicao de tempo.
    return hmac.compare_digest(segredo_hash, hash_de(segredo or ""))
