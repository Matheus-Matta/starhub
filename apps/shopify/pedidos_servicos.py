"""Servicos extras contratados nas propriedades do item do Shopify.

    {"name": "_impermeabilizacao_123", "value": "Sim [+ R$ 499,99]"}
    -> {"servico": "Impermeabilização da poltrona", "opcao": "Sim", "preco": Decimal("499.99")}

Recusa ("Não"), valor vazio ou sem preco positivo nao e servico contratado.
"""

import re

from apps.loja.dinheiro import ValorInvalido, dinheiro
from apps.loja.services.extras_pedido import RECUSAS, rotulo_servico

_PRECO = re.compile(r"[\[(]\s*\+?\s*R\$\s*(?P<valor>[\d.,]+)\s*[\])]")
_IGNORADAS = {"_tpo_add_by"}


def _preco(texto):
    achado = _PRECO.search(texto or "")
    if not achado:
        return None
    bruto = achado["valor"]
    # "1.499,99" e o formato brasileiro; "499.99" ja vem com ponto decimal.
    if "," in bruto:
        bruto = bruto.replace(".", "").replace(",", ".")
    try:
        return dinheiro(bruto)
    except ValorInvalido:
        return None


def _rotulo(nome):
    return rotulo_servico(_PRECO.sub("", nome))


def servicos_do_item(propriedades):
    servicos = []
    for propriedade in propriedades or []:
        nome = str(propriedade.get("name") or "").strip()
        texto = str(propriedade.get("value") or "").strip()
        if not nome or nome in _IGNORADAS:
            continue
        opcao = _PRECO.sub("", texto).strip()
        if not opcao or opcao.casefold() in RECUSAS:
            continue
        preco = _preco(texto) or _preco(nome)
        if not preco or preco <= 0:
            continue
        servicos.append({"servico": _rotulo(nome), "opcao": opcao, "preco": preco})
    return servicos
