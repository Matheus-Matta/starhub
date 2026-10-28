"""Servicos do hub como dimensions do produto no Suri (que nao tem servico).

    Sofa (Branco padrao, Preto) + Simples e Completa (categoria Instalacao) + Imper
    (categoria Impermeabilizacao)
    -> attributes: Cor | Instalação: Sem serviço, Completa (R$ 40,00), Simples (R$ 20,00)
                   | Impermeabilização: Sem serviço, Imper (R$ 30,00)
    -> dimensions: Branco e Preto, as duas "Sem serviço" em cada categoria, e uma por
                   servico: SKU do servico, sem combinar com as cores.

Cada categoria e um atributo, na ordem dela; servico sem categoria vai no atributo
"Serviço". "Sem serviço" vem primeiro: o Suri abre marcado nele. O nome da opcao leva
o preco porque o Suri nao mostra quanto cada opcao soma.

A dimension do servico vende a variante padrao com o servico: as outras opcoes (Cor)
sao as dela, nunca "Qualquer"; preco = variante padrao + servico, com o estoque, as
medidas e a foto dela (a do servico, se tiver). No pedido o hub tira o servico do
valor do item (importar_itens.py).

Toda dimension tem valor em todos os atributos, ou o Suri recusa o produto inteiro
(ProductAttributtesAndDimensionsMustMatch): por isso toda categoria tem "Sem serviço",
o valor das cores e dos servicos das outras categorias nela.
"""

from apps.core.ui.formatos import moeda
from apps.integracoes.url_publica import url_publica
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


def _foto(configuracao, servico):
    imagem = servico.imagem if isinstance(servico.imagem, dict) else {}
    url = url_publica(configuracao, imagem.get("src")) if configuracao else ""
    return url, imagem.get("alt") or servico.nome


def _do_servico(padrao, servico, preco, valores, configuracao):
    url, descricao = _foto(configuracao, servico)
    return {**padrao, "sku": servico.sku, "dimensions": {**padrao["dimensions"], **valores},
            "price": padrao["price"] + preco,
            "image": produtos_dimensoes.imagem(url, descricao) if url else padrao["image"],
            "stocks": {loja: dict(estoque) for loja, estoque in padrao["stocks"].items()}}


def dimensoes(servicos, base, sku_padrao, configuracao=None):
    """(dimensions, do_servico): {sku do servico: {"variante", "servico", "preco"}}."""
    por_atributo = grupos(servicos)
    if not por_atributo:
        return base, {}
    vazio = dict.fromkeys(por_atributo, SEM_SERVICO)
    saida = [{**d, "dimensions": {**d["dimensions"], **vazio}} for d in base]
    padrao = next((d for d in base if d["sku"] == sku_padrao), base[0])
    skus, do_servico = {d["sku"] for d in base}, {}
    for nome, pares in por_atributo.items():
        for servico, preco in pares:
            if servico.sku in skus:  # SKU repetido derrubaria o PUT do produto inteiro
                continue
            skus.add(servico.sku)
            saida.append(_do_servico(padrao, servico, preco,
                                     {**vazio, nome: rotulo(servico, preco)}, configuracao))
            do_servico[servico.sku] = {"variante": padrao["sku"], "servico": servico,
                                       "preco": preco}
    return saida, do_servico
