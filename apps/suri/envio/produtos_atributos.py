"""Atributos e dimensions do produto no Suri, sempre batendo entre si.

O Suri recusa o produto (HTTP 400 ProductAttributtesAndDimensionsMustMatch) quando uma
dimension nao tem exatamente os atributos do produto, com valor entre as opcoes, ou
quando duas repetem a mesma combinacao. Casos que o hub tinha e o Suri recusava:

    produto simples com servico:  attributes [Serviços]  dimension do produto {}
    simples cuja variante tem Cor: attributes []          dimension {"Cor": "Azul"}
    variavel sem opcoes:           dimensions {} e {} (iguais)

Aqui: os atributos saem de todas as dimensions. Variantes que o Suri veria iguais, ou
que nao tem as mesmas opcoes (uma com Cor, outra sem), vao pelo titulo, no atributo
"Variação": preencher a que falta com "Qualquer" punha uma opcao falsa a venda. Os
servicos (servicos_dimensoes.py) ja chegam com todos os atributos deles.
"""

VARIACAO = "Variação"


def distinguir(dimensoes, variantes):
    """Variantes iguais ou com opcoes diferentes ganham o titulo como "Variação"."""
    combinacoes = [tuple(sorted(d["dimensions"].items())) for d in dimensoes]
    mesmas_opcoes = len({frozenset(d["dimensions"]) for d in dimensoes}) == 1
    if len(dimensoes) < 2 or (mesmas_opcoes and len(set(combinacoes)) == len(combinacoes)):
        return
    vistos = set()
    for dimensao, variante in zip(dimensoes, variantes, strict=True):
        nome = (variante.titulo or "").strip() or dimensao["sku"]
        if nome in vistos:  # titulo repetido: o SKU desempata
            nome = f"{nome} ({dimensao['sku']})"
        vistos.add(nome)
        dimensao["dimensions"] = {VARIACAO: nome}


def alinhar(dimensoes):
    """Attributes que batem com as dimensions, na ordem em que as opcoes aparecem."""
    nomes = []
    for dimensao in dimensoes:
        nomes += [nome for nome in dimensao["dimensions"] if nome not in nomes]
    opcoes = {nome: [] for nome in nomes}
    for dimensao in dimensoes:
        valores = dimensao["dimensions"]
        for nome in nomes:
            if {"name": valores[nome]} not in opcoes[nome]:
                opcoes[nome].append({"name": valores[nome]})
        dimensao["dimensions"] = {nome: valores[nome] for nome in nomes}
    return [{"name": nome, "options": opcoes[nome]} for nome in nomes]
