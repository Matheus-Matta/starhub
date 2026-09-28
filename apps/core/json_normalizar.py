"""Normaliza o JSON que os widgets do tema mandam, por tipo de campo.

O widget (JS) ja monta a estrutura certa, mas quem garante e o servidor: um
POST feito a mao, ou um JS antigo em cache, nao pode gravar lixo que depois
quebra a API Woo ou o calculo do pedido. Cada funcao recebe o valor ja
decodificado (json.loads) e devolve o valor limpo, ou levanta ValidationError.
"""

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ValidationError

CENTAVO = Decimal("0.01")


def _lista_de_objetos(valor, rotulo):
    if valor in (None, ""):
        return []
    if not isinstance(valor, list) or not all(isinstance(item, dict) for item in valor):
        raise ValidationError(f"{rotulo}: formato invalido (esperava uma lista).")
    return valor


def _proximo_id(itens):
    return max((item.get("id", 0) for item in itens if isinstance(item.get("id"), int)),
               default=0) + 1


def dinheiro_texto(valor, rotulo):
    """ "10,5" -> "10.50". Texto, nunca float (e o formato do Woo)."""
    texto = str(valor if valor is not None else "").strip().replace(" ", "")
    if not texto:
        return "0.00"
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return f"{Decimal(texto).quantize(CENTAVO, rounding=ROUND_HALF_UP):.2f}"
    except InvalidOperation as erro:
        raise ValidationError(f"{rotulo}: '{valor}' nao e um valor em reais.") from erro


def tags(valor, **_):
    """Aceita ["a", {"name": "b", "id": 3}]; devolve objetos no formato Woo,
    sem repetir (ignora maiusculas) e mantendo id/slug de quem ja tinha."""
    if valor in (None, ""):
        return []
    if not isinstance(valor, list):
        raise ValidationError("Tags: formato invalido (esperava uma lista).")
    vistos, saida = set(), []
    for item in valor:
        objeto = dict(item) if isinstance(item, dict) else {"name": item}
        nome = str(objeto.get("name") or "").strip()
        if not nome or nome.casefold() in vistos:
            continue
        vistos.add(nome.casefold())
        objeto["name"] = nome
        saida.append(objeto)
    return saida


def textos(valor, **_):
    """Lista de textos simples (escopos da chave de API): ["read", "write"]."""
    if valor in (None, ""):
        return []
    if not isinstance(valor, list):
        raise ValidationError("Formato invalido (esperava uma lista).")
    vistos, saida = set(), []
    for item in valor:
        texto = str(item.get("name", "") if isinstance(item, dict) else item).strip()
        if texto and texto.casefold() not in vistos:
            vistos.add(texto.casefold())
            saida.append(texto)
    return saida


def valor_livre(valor):
    """Coluna "valor": o texto digitado vira o tipo que ele representa.

    "10" -> 10, "true" -> True, '["a", "b"]' -> lista; o que nao e JSON fica
    texto ("shopify"). Para gravar o TEXTO "10", digite com aspas: "10".
    """
    if not isinstance(valor, str):
        return valor
    texto = valor.strip()
    if not texto:
        return ""
    try:
        return json.loads(texto)
    except ValueError:
        return texto


def chave_valor(valor, **_):
    """meta_data: [{"id", "key", "value"}]. Linha sem chave some; linha nova ganha id."""
    itens = [dict(item) for item in _lista_de_objetos(valor, "Metadados")]
    saida = [item for item in itens if str(item.get("key") or "").strip()]
    proximo = _proximo_id(saida)
    for item in saida:
        item["key"] = str(item["key"]).strip()
        item.setdefault("value", "")
        if not isinstance(item.get("id"), int):
            item["id"] = proximo
            proximo += 1
    return saida


def _celula(coluna, valor, rotulo):
    tipo = coluna.get("tipo", "texto")
    if tipo == "valor":
        return valor_livre(valor)
    if tipo == "escolha":
        opcoes = [opcao["valor"] for opcao in coluna.get("opcoes", [])]
        if valor not in opcoes:
            raise ValidationError(f"{rotulo}: escolha uma das opcoes.")
        return valor
    if tipo == "dinheiro":
        return dinheiro_texto(valor, rotulo)
    if tipo == "switch":
        return bool(valor)
    if tipo == "tags":
        return [str(v).strip() for v in (valor or []) if str(v).strip()]
    if tipo == "numero":
        try:
            return int(valor or 0)
        except (TypeError, ValueError) as erro:
            raise ValidationError(f"{rotulo}: '{valor}' nao e um numero inteiro.") from erro
    return str(valor if valor is not None else "").strip()


def lista(valor, colunas, rotulo="Lista", com_id=False, **_):
    """Linhas de uma tabela (frete, taxas, cupons, atributos). Linha com todas
    as colunas vazias some; chaves que o widget nao mostra (taxes, meta_data)
    sao mantidas."""
    saida = []
    for item in _lista_de_objetos(valor, rotulo):
        linha = dict(item)
        vazia = True
        for coluna in colunas:
            bruto = linha.get(coluna["campo"])
            if bruto not in (None, "", [], False):
                vazia = False
            linha[coluna["campo"]] = _celula(coluna, bruto, f"{rotulo} / {coluna['rotulo']}")
        if not vazia:
            saida.append(linha)
    if com_id:
        proximo = _proximo_id(saida)
        for linha in saida:
            if not isinstance(linha.get("id"), int):
                linha["id"], proximo = proximo, proximo + 1
    return saida


def objeto(valor, campos, extras=True, rotulo="Campo", **_):
    """Dicionario (endereco, dimensoes, configuracoes). Campos conhecidos viram
    texto; os extras (cpf, persontype...) ficam se extras=True, com o tipo que
    tinham: numero continua numero e objeto aninhado continua objeto."""
    if valor in (None, ""):
        valor = {}
    if not isinstance(valor, dict):
        raise ValidationError(f"{rotulo}: formato invalido (esperava um objeto).")
    conhecidos = {campo["campo"] for campo in campos}
    saida = {}
    for chave, bruto in valor.items():
        chave = str(chave).strip()
        if not chave or (chave not in conhecidos and not extras):
            continue
        if chave not in conhecidos and not isinstance(bruto, str) and bruto is not None:
            saida[chave] = bruto
            continue
        texto = "" if bruto is None else str(bruto).strip()
        if chave in conhecidos or texto:
            saida[chave] = texto
    return saida
