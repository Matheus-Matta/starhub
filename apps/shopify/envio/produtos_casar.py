"""Qual variante da loja e cada variante do hub no update: SKU primeiro, depois o id.

A resposta do productUpdate traz as variantes do produto na loja (id, sku, item de
estoque) e os nomes das opcoes. Com elas:

1. SKU igual -> e essa (vale mais que o vinculo: vinculo velho ou trocado se corrige);
2. o vinculo (ExternalReference "variantes"), se o id ainda existe no produto da loja;
3. uma variante de cada lado -> e a mesma (SKU trocado no hub);
4. nenhuma -> variante nova, criada pelo productVariantsBulkCreate.

Antes, vinculo para variante que nao existia mais derrubava o update inteiro ("Product
variant does not exist") e variante sem vinculo que ja estava na loja ia para o create
com a opcao padrao "Title" ("Option does not exist"): o preco alterado nunca chegava.
"""

import logging

from apps.shopify.contexto import avisar
from apps.shopify.envio import produtos_variantes as variantes_shopify

logger = logging.getLogger(__name__)
LIMITE = 250  # variants(first: 250) do ATUALIZAR em produtos.py


def _sku(valor):
    return (valor or "").strip()


def da_loja(produto):
    """(variantes, nomes das opcoes) da resposta, ou (None, None) se ela nao trouxe."""
    variantes = ((produto or {}).get("variants") or {}).get("nodes")
    if variantes is None:
        return None, None
    return variantes, {o.get("name") for o in (produto or {}).get("options") or []}


def casar(enviador, variantes, loja, vinculos, produto_gid):
    """{pk da variante do hub: gid da loja}; regrava o vinculo que mudou."""
    livres = {n["id"]: n for n in loja}
    escolhidas = {}
    for variante in variantes:
        sku = _sku(variante.sku)
        achada = next((n for n in livres.values() if sku and _sku(n.get("sku")) == sku), None)
        if achada:
            escolhidas[variante.pk] = livres.pop(achada["id"])
    for variante in variantes:
        externo = vinculos.get(str(variante.pk))
        if variante.pk not in escolhidas and externo in livres:
            escolhidas[variante.pk] = livres.pop(externo)
    if len(variantes) == 1 and len(loja) == 1 and not escolhidas and livres:
        escolhidas[variantes[0].pk] = livres.popitem()[1]
    if len(loja) >= LIMITE:
        # Lista cortada em 250: a variante ligada que ficou de fora segue pelo vinculo,
        # em vez de virar "nova" e ser criada de novo.
        for variante in variantes:
            externo = vinculos.get(str(variante.pk))
            if variante.pk not in escolhidas and externo:
                escolhidas[variante.pk] = {"id": externo}
    for variante in variantes:
        achada = escolhidas.get(variante.pk)
        if achada and vinculos.get(str(variante.pk)) != achada["id"]:
            variantes_shopify.vincular(enviador, variante, achada, produto_gid)
    return {pk: n["id"] for pk, n in escolhidas.items()}


def no_lote(variante, opcoes_da_loja):
    """Entrada do productVariantsBulkUpdate; leva as opcoes (Cor: Verde) so quando a
    variante tem opcao cadastrada e a loja tem todas elas: opcao que a loja nao tem
    derrubaria o lote inteiro, preco junto."""
    dados = variantes_shopify.em_lote(variante)
    if opcoes_da_loja and variante.opcoes.exists():
        pares = variantes_shopify.opcoes_da_variante(variante, True)
        if all(nome in opcoes_da_loja for nome, _valor in pares):
            dados["optionValues"] = variantes_shopify.valores_de_opcao(pares)
    return dados


def criaveis(novas, varias, opcoes_da_loja):
    """Variantes novas que a loja aceita criar. Opcao que o produto da loja nao tem
    ("Option does not exist") derrubava o envio inteiro: essa fica de fora, com aviso,
    e o resto (preco, estoque, dados das outras) segue."""
    if not opcoes_da_loja:
        return novas
    aceitas = []
    for variante in novas:
        nomes = [nome for nome, _ in variantes_shopify.opcoes_da_variante(variante, varias)]
        faltam = [nome for nome in nomes if nome not in opcoes_da_loja]
        if not faltam:
            aceitas.append(variante)
            continue
        tem = ", ".join(sorted(opcoes_da_loja))
        texto = (f"Variante {variante.sku or variante.pk} nao criada no Shopify: o produto "
                 f"la nao tem a opcao {', '.join(faltam)} (tem {tem}). Use o mesmo SKU da "
                 "variante da loja ou cadastre as opcoes iguais.")
        logger.warning(texto)
        avisar(texto, recurso="variantes", id=str(variante.pk), descricao=variante.titulo)
    return aceitas
