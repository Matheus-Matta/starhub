"""Custo pedido de uma consulta GraphQL do Shopify, calculado pelo texto da query.

Regra da doc de limites (Admin GraphQL): "Object | 1", "Scalar | 0", "Connection |
Sized by `first` and `last` arguments" (2 + first x custo do no) e "A single query may
not exceed a cost of 1,000 points". O calculo segue a mesma conta escrita na docstring
de consultas_produtos.py, para a docstring e o teste nao divergirem.
"""

import re

TOKEN = re.compile(r"\.\.\.\s*on\s+\w+\s*\{|(\w+)\s*(\([^)]*\))?\s*\{|\}")


def custo(query):
    """Soma objetos (1) e conexoes (2) multiplicados pelos `first` de fora.

    `nodes` de uma conexao custa 1 por item pedido; fragmento (`... on X`) e a raiz
    (`query`) nao custam. Lista simples de objetos (selectedOptions) conta 1, como
    na docstring.
    """
    total, pilha = 0, [1]
    for achado in TOKEN.finditer(query):
        texto, nome, argumentos = achado.group(0), achado.group(1), achado.group(2)
        if texto == "}":
            pilha.pop()
            continue
        fora = pilha[-1]
        first = re.search(r"first:\s*(\d+)", argumentos or "")
        if nome is None or nome == "query":
            pilha.append(fora)
        elif first:
            total += 2 * fora
            pilha.append(fora * int(first.group(1)))
        elif nome == "pageInfo":
            # pageInfo fica fora de `nodes`: um por conexao, nao um por item.
            total += _fora_da_conexao(pilha)
            pilha.append(fora)
        else:
            total += fora
            pilha.append(fora)
    return total


def _fora_da_conexao(pilha):
    return pilha[-2] if len(pilha) > 1 else pilha[-1]
