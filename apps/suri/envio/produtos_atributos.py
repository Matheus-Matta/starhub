"""Atributos e dimensions do produto no Suri, sempre batendo entre si.

O Suri recusa o produto (HTTP 400 ProductAttributtesAndDimensionsMustMatch) quando uma
dimension nao tem exatamente os atributos do produto, com valor entre as opcoes, ou
quando duas repetem a mesma combinacao. Casos que o hub tinha e o Suri recusava:

    produto simples com servico:  attributes [Serviços]  dimension do produto {}
    simples cuja variante tem Cor: attributes []          dimension {"Cor": "Azul"}
    variavel sem opcoes:           dimensions {} e {} (iguais)

Aqui: os atributos saem de todas as dimensions; a que nao tem um deles recebe um valor
de preenchimento ("Sem serviço" no atributo do servico, "Qualquer" nos outros); variavel
sem opcoes diferencia as variantes pelo titulo, no atributo "Variação".
"""

from apps.suri.servicos import ATRIBUTO as SERVICOS

VARIACAO = "Variação"
SEM_SERVICO = "Sem serviço"
QUALQUER = "Qualquer"


def distinguir(dimensoes, variantes):
    """Variantes que o Suri veria iguais ganham o titulo como opcao "Variação"."""
    combinacoes = [tuple(sorted(d["dimensions"].items())) for d in dimensoes]
    if len(dimensoes) < 2 or len(set(combinacoes)) == len(combinacoes):
        return
    vistos = set()
    for dimensao, variante in zip(dimensoes, variantes, strict=True):
        nome = (variante.titulo or "").strip() or dimensao["sku"]
        if nome in vistos:  # titulo repetido: o SKU desempata
            nome = f"{nome} ({dimensao['sku']})"
        vistos.add(nome)
        dimensao["dimensions"] = {VARIACAO: nome}


def alinhar(dimensoes):
    """Completa as dimensions e devolve os attributes que batem com elas."""
    nomes = []
    for dimensao in dimensoes:
        nomes += [nome for nome in dimensao["dimensions"] if nome not in nomes]
    opcoes = {nome: [] for nome in nomes}
    for dimensao in dimensoes:
        valores = dimensao["dimensions"]
        for nome in nomes:
            if nome not in valores:
                valores[nome] = SEM_SERVICO if nome == SERVICOS else QUALQUER
            if {"name": valores[nome]} not in opcoes[nome]:
                opcoes[nome].append({"name": valores[nome]})
        dimensao["dimensions"] = {nome: valores[nome] for nome in nomes}
    return [{"name": nome, "options": opcoes[nome]} for nome in nomes]
