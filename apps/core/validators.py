"""Validadores de documento e contato (formularios e clean() dos models).

Cada um aceita o valor com ou sem mascara ("123.456.789-09" ou "12345678909")
e levanta ValidationError com mensagem para o usuario. Vazio passa: quem exige
preenchimento e o blank=False do campo.
"""

import re

from django.core.exceptions import ValidationError

UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)


def somente_digitos(value):
    return re.sub(r"\D", "", value or "")


def _digito(numeros, pesos):
    resto = sum(int(n) * p for n, p in zip(numeros, pesos, strict=False)) % 11
    return 0 if resto < 2 else 11 - resto


def validar_cpf(value):
    cpf = somente_digitos(value)
    if not cpf:
        return
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        raise ValidationError("CPF invalido.")
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        if (soma * 10 % 11) % 10 != int(cpf[tamanho]):
            raise ValidationError("CPF invalido.")


def validar_cnpj(value):
    cnpj = somente_digitos(value)
    if not cnpj:
        return
    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    if (
        len(cnpj) != 14 or cnpj == cnpj[0] * 14
        or _digito(cnpj, pesos) != int(cnpj[12])
        or _digito(cnpj, [6, *pesos]) != int(cnpj[13])
    ):
        raise ValidationError("CNPJ invalido.")


def validar_documento(value):
    """CPF (11 digitos) ou CNPJ (14): decide pelo tamanho."""
    numeros = somente_digitos(value)
    if len(numeros) > 11:
        validar_cnpj(numeros)
    else:
        validar_cpf(numeros)


def validar_telefone(value):
    """DDD + numero (10 ou 11 digitos) ou internacional com "+" (8 a 15 digitos)."""
    if not value:
        return
    numeros = somente_digitos(value)
    internacional = str(value).strip().startswith("+")
    if not (8 <= len(numeros) <= 15) or (not internacional and len(numeros) not in (10, 11)):
        raise ValidationError("Telefone invalido: informe DDD + numero, ex.: (81) 99999-9999.")


def validar_gtin(value):
    """Codigo de barras EAN/GTIN (8, 12, 13 ou 14 digitos) com digito verificador."""
    if not value:
        return
    codigo = str(value).strip()
    if not codigo.isdigit() or len(codigo) not in (8, 12, 13, 14):
        raise ValidationError("Codigo de barras invalido: use 8, 12, 13 ou 14 digitos.")
    corpo = codigo[:-1][::-1]
    soma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(corpo))
    if (10 - soma % 10) % 10 != int(codigo[-1]):
        raise ValidationError("Codigo de barras invalido: o digito verificador nao confere.")


def validar_uf(value):
    if value and str(value).upper() not in UFS:
        raise ValidationError("UF invalida: use a sigla do estado, ex.: PE.")
