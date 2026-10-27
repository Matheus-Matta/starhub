"""Campos comuns de uma dimension no contrato de produto do Suri."""

from decimal import Decimal, InvalidOperation


def _numero(valor):
    try:
        return Decimal(str(valor or 0).replace(",", "."))
    except InvalidOperation:
        return Decimal("0")


def imagem(url="", descricao=None):
    url = url or ""
    return {"providerId": None, "url": url,
            "description": (descricao or None) if url else None}


def medidas(variante=None):
    dimensoes = variante.dimensions if variante and isinstance(variante.dimensions, dict) else {}
    peso = (_numero(variante.weight) * 1000).to_integral_value() if variante else Decimal("0")
    return {
        "weightInGrams": peso,
        "heightInCm": _numero(dimensoes.get("height")),
        "widthInCm": _numero(dimensoes.get("width")),
        "lengthInCm": _numero(dimensoes.get("length")),
        "unitsPerPackage": 1,
    }


def completar(dimensao, variante=None, url="", descricao=None):
    """Evita propriedades nulas que fazem o endpoint do Suri falhar com `source`."""
    return {
        **dimensao,
        "image": imagem(url, descricao),
        "measurements": medidas(variante),
        "priceTables": {},
    }
