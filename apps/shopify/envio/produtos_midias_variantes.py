"""Foto de cada variacao do hub -> imagem da variante no Shopify (`mediaId`).

As fotos sobem para o produto (produtos_midias.py), mas nenhuma era ligada a variante:
na loja todas as cores mostravam a foto principal. Aqui cada variante vinculada (achada
pelo SKU e depois pelo id, produtos_casar.py) recebe a primeira foto da sua linha no hub.

O Shopify recusa ligar midia que ainda nao esta pronta ("Non-ready media cannot be
attached to variants"): a foto recem-enviada fica PROCESSING por alguns segundos, entao
a tarefa espera um pouco. A que nao ficar pronta liga no proximo envio do produto.
Falha aqui nao derruba o envio: no create o produto ja existe na loja e, sem o vinculo,
a nova tentativa criaria o produto duplicado.
"""

import logging
import time

from apps.loja.models import MidiaProduto
from apps.shopify import midias as vinculos
from apps.shopify.cliente import ShopifyErro

logger = logging.getLogger(__name__)

LIGAR = """mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants { id } userErrors { field message }
  }
}"""
TENTATIVAS = 5
ESPERA = 2  # segundos entre as consultas de midia pronta


def _fotos(produto):
    return list(produto.midias.filter(tipo=MidiaProduto.Tipo.IMAGEM).order_by("posicao", "id"))


def _midia_na_loja(produto, fotos):
    """{pk da foto do hub: (gid da MediaImage, pronta?)}. A mesma URL ligada a duas linhas
    (a do produto e a da variante) e uma midia so na loja: a linha sem vinculo usa a da
    outra."""
    por_foto, por_url = {}, {}
    for vinculo in vinculos.do_produto(produto, fotos):
        if vinculo.external_id.startswith(vinculos.PENDENTE):
            continue
        dado = (vinculo.external_id, bool((vinculo.metadata or {}).get("shopify_src")))
        por_foto[vinculo.object_id] = dado
        por_url.setdefault((vinculo.metadata or {}).get("enviado_src"), dado)
    for foto in fotos:
        por_url.setdefault(foto.url, por_foto.get(str(foto.pk)))
    return {str(f.pk): por_foto.get(str(f.pk)) or por_url.get(f.url) for f in fotos}


def desejadas(enviador, produto, variantes):
    """{gid da variante na loja: (gid da midia, pronta?)} das variacoes com foto propria."""
    if len(variantes) < 2:
        return {}  # Simples: a foto do produto ja e a da unica variante.
    fotos = _fotos(produto)
    na_loja = _midia_na_loja(produto, fotos)
    gids = dict(enviador.referencias_variantes().filter(
        object_id__in=[str(v.pk) for v in variantes]).values_list("object_id", "external_id"))
    saida = {}
    for variante in variantes:
        foto = next((f for f in fotos if f.variante_id == variante.pk), None)
        midia = na_loja.get(str(foto.pk)) if foto else None
        if midia and str(variante.pk) in gids:
            saida[gids[str(variante.pk)]] = midia
    return saida


def _prontas(enviador, pedidas):
    prontas = {gid for gid, pronta in pedidas.values() if pronta}
    faltam = {gid for gid, _ in pedidas.values()} - prontas
    for tentativa in range(TENTATIVAS):
        if not faltam:
            break
        if tentativa:
            time.sleep(ESPERA)
        achadas = set(vinculos.cdn_por_id(enviador.cliente, sorted(faltam)))
        prontas |= achadas
        faltam -= achadas
    return prontas


def ligar(enviador, produto, variantes, produto_gid):
    pedidas = desejadas(enviador, produto, variantes)
    if not pedidas:
        return
    try:
        prontas = _prontas(enviador, pedidas)
        entrada = [{"id": variante, "mediaId": midia}
                   for variante, (midia, _) in pedidas.items() if midia in prontas]
        if entrada:
            enviador.mutacao(LIGAR, {"productId": produto_gid, "variants": entrada},
                             "productVariantsBulkUpdate")
    except ShopifyErro as erro:
        logger.warning("Fotos das variacoes do produto %s nao ligadas na Shopify (%s); o "
                       "proximo envio do produto tenta de novo.", produto.pk, erro)
        return
    if len(entrada) < len(pedidas):
        logger.warning("Produto %s: %s foto(s) de variacao ainda em processamento na "
                       "Shopify; ligam no proximo envio.", produto.pk,
                       len(pedidas) - len(entrada))
