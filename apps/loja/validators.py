from django.core.exceptions import ValidationError

# CPF/CNPJ/telefone moram em apps/core/validators.py (o Address do core usa tambem).
from apps.core.validators import (  # noqa: F401  (reexportados para quem ja importa daqui)
    somente_digitos,
    validar_cnpj,
    validar_cpf,
    validar_telefone,
)


def normalizar_telefone(value):
    """Grava so os digitos. Aceita qualquer tamanho plausivel (8 a 15): o ERP e
    os marketplaces mandam numero estrangeiro. O form usa validar_telefone, mais estrito."""
    telefone = somente_digitos(value)
    if telefone and not 8 <= len(telefone) <= 15:
        raise ValidationError("Telefone invalido.")
    return telefone
