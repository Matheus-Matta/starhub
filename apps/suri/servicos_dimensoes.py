"""Servicos do hub como dimensions do produto no Suri (que nao tem servico).

    Sofa (Branco padrao, Preto) + Simples e Completa (categoria Instalacao) + Imper
    (categoria Impermeabilizacao)
    -> attributes: Cor | Instalação: Sem serviço, Completa (R$ 40,00), Simples (R$ 20,00)
                   | Impermeabilização: Sem serviço, Imper (R$ 30,00)
    -> dimensions: toda cor com toda escolha (2 x 3 x 2 = 12), cada uma com SKU proprio:
                   Branco + Imper = IMP; Preto + Simples + Imper = INS1-IMP-PRETO.

O Suri so vende a combinacao que existe como dimension: com uma dimension por servico,
presa a cor padrao, o cliente nao levava Preto com servico nem dois servicos juntos.
Dentro de uma categoria vai um servico so (o atributo tem um valor por vez); servico
sem categoria vai no atributo "Serviço". "Sem serviço" vem primeiro: o Suri abre
marcado nele. O nome da opcao leva o preco porque o Suri nao mostra quanto cada opcao
soma.

A dimension combinada vende a cor dela com os servicos: preco = cor + servicos, estoque
e medidas da cor, foto do primeiro servico que tiver uma. Kit (bundle) usa o maior
estoque das pecas (estoque()). No pedido o hub tira os servicos do valor do item
(importar_itens.py). O SKU da cor padrao com um servico so e o do servico, como antes
das combinacoes: pedido ja feito com ele continua achando o vinculo.

Toda dimension tem valor em todos os atributos, ou o Suri recusa o produto inteiro
(ProductAttributtesAndDimensionsMustMatch).
"""

from itertools import product

from apps.core.ui.formatos import moeda
from apps.integracoes.url_publica import url_publica
from apps.loja.models import Produto
from apps.suri.envio import produtos_dimensoes

ATRIBUTO = "Serviço"
SEM_SERVICO = "Sem serviço"


def _atributo(servico):
    return servico.categoria.nome if servico.categoria_id else ATRIBUTO


def _ordem(par):
    categoria = par[0].categoria
    return (0, categoria.ordem, categoria.nome) if categoria else (1, 0, "")


def rotulo(servico, preco):
    return f"{servico.nome} ({moeda(preco)})"


def grupos(servicos):
    """{atributo: [(servico, preco)]} na ordem das categorias e, nelas, das regras."""
    por_atributo = {}
    for par in sorted(servicos, key=_ordem):
        por_atributo.setdefault(_atributo(par[0]), []).append(par)
    return por_atributo


def estoque(produto):
    """Estoque da dimension do servico: simples, o dele; variavel, a variacao com mais;
    kit (bundle), o item com mais. O servico nao acaba enquanto houver peca para levar."""
    if produto.tipo == Produto.Tipo.BUNDLE:
        quantidades = produto.componentes.values_list(
            "component_variant__inventory_quantity", flat=True)
    else:
        quantidades = produto.variantes.values_list("inventory_quantity", flat=True)
    return max((max(q, 0) for q in quantidades), default=0)


def _foto(configuracao, pares):
    for servico, _ in pares:
        imagem = servico.imagem if isinstance(servico.imagem, dict) else {}
        if imagem.get("src") and configuracao:
            return url_publica(configuracao, imagem["src"]), imagem.get("alt") or servico.nome
    return "", None


def _escolhas(por_atributo):
    """({atributo: valor}, [(servico, preco)]) de cada jeito de escolher uma opcao por
    atributo, menos "Sem serviço" em todos (essa e a propria cor)."""
    nomes = list(por_atributo)
    for escolha in product(*([None, *pares] for pares in por_atributo.values())):
        pares = [par for par in escolha if par]
        if pares:
            yield ({nome: rotulo(*par) if par else SEM_SERVICO
                    for nome, par in zip(nomes, escolha, strict=True)}, pares)


def _sku(pares, cor, padrao):
    servicos = "-".join(servico.sku for servico, _ in pares)
    return servicos if cor is padrao else f"{servicos}-{cor['sku']}"


def _combinada(cor, sku, pares, valores, configuracao, quantidade):
    url, descricao = _foto(configuracao, pares)
    estoques = cor["stocks"] if quantidade is None else {
        loja: {"stock": quantidade} for loja in cor["stocks"]}
    return {**cor, "sku": sku, "dimensions": {**cor["dimensions"], **valores},
            "price": cor["price"] + sum(preco for _, preco in pares),
            "image": produtos_dimensoes.imagem(url, descricao) if url else cor["image"],
            "stocks": estoques}


def dimensoes(servicos, base, sku_padrao, configuracao=None, quantidade=None):
    """(dimensions, combinadas): {sku: {"variante", "servicos": [(servico, preco)]}}.

    `quantidade` None = cada combinacao com o estoque da cor; kit passa estoque()."""
    por_atributo = grupos(servicos)
    if not por_atributo:
        return base, {}
    vazio = dict.fromkeys(por_atributo, SEM_SERVICO)
    saida = [{**d, "dimensions": {**d["dimensions"], **vazio}} for d in base]
    padrao = next((d for d in base if d["sku"] == sku_padrao), base[0])
    skus, combinadas = {d["sku"] for d in base}, {}
    for valores, pares in _escolhas(por_atributo):
        for cor in (padrao, *(d for d in base if d is not padrao)):
            sku = _sku(pares, cor, padrao)
            if sku in skus:  # SKU repetido derrubaria o PUT do produto inteiro
                continue
            skus.add(sku)
            saida.append(_combinada(cor, sku, pares, valores, configuracao, quantidade))
            combinadas[sku] = {"variante": cor["sku"], "servicos": pares}
    return saida, combinadas
