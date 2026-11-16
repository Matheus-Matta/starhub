"""Servicos extras contratados nas propriedades do item do Shopify (app Easify).

    {"name": "_IMPER ATÉ 2,5M_2432", "value": "IMPERMEABILIZAÇÃO [ +R$ 499,99 ]"}
    -> {"servico": "IMPER ATÉ 2,5M", "_sku": "2432", "opcao": "IMPERMEABILIZAÇÃO",
        "preco": Decimal("499.99")}

O "_sku" e o SKU do cadastro de Servicos: loja.services.servicos.vincular liga por ele
e cria o cadastro que faltar. Recusa ("Não"), valor vazio ou sem preco positivo nao
e servico contratado.
"""

import re

from apps.loja.dinheiro import ValorInvalido, dinheiro
from apps.loja.services.extras_pedido import RECUSAS, rotulo_servico

_PRECO = re.compile(r"[\[(]\s*\+?\s*R\$\s*(?P<valor>[\d.,]+)\s*[\])]")
_IGNORADAS = {"_tpo_add_by"}
# Nome guloso: o SKU e so o que vem depois do ultimo "_" ("_IMPER_ATE_2432" -> 2432).
_NOME_E_SKU = re.compile(r"^_?(?P<nome>.+)_(?P<sku>[^_\s]+)$")


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


def _nome_e_sku(nome):
    limpo = _PRECO.sub("", nome).strip()
    achado = _NOME_E_SKU.match(limpo)
    nome_servico = achado["nome"].strip(" _") if achado else ""
    if nome_servico:
        return {"servico": nome_servico[:150], "_sku": achado["sku"][:100]}
    # Sem SKU no fim do nome: o cadastro e achado pelo nome, como antes do Easify.
    return {"servico": rotulo_servico(limpo)}


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
        servicos.append({**_nome_e_sku(nome), "opcao": opcao, "preco": preco})
    return servicos
