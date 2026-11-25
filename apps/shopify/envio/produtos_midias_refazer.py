"""Sincronizar > Exportar (e o botao do produto): as fotos da loja saem e vao as do hub.

A ordem protege a loja: manda as novas, espera ficarem prontas e so entao apaga TODAS as
antigas (com ou sem vinculo). Nova que nao fica pronta (URL do hub fora do ar, arquivo
recusado) e desfeita e as antigas continuam. Hub sem foto nao apaga as da loja.
"""

import time

from apps.shopify import midias as vinculos
from apps.shopify.cliente import ShopifyErro
from apps.shopify.contexto import avisar
from apps.shopify.envio import produtos_midias as midias_shopify
from apps.shopify.midias_apagadas import MARCA, ids_na_loja

ACRESCENTAR = """mutation($product: ProductUpdateInput!, $media: [CreateMediaInput!]) {
  productUpdate(product: $product, media: $media) {
    product { id media(first: 250) { nodes { id } } } userErrors { field message }
  }
}"""
MAXIMO = 250  # midias por produto no Shopify
TENTATIVAS, ESPERA = 20, 2  # ate 40 s


def _grupos(enviador, fotos):
    """[(url publica, [linhas])]: a mesma foto em duas variacoes e uma midia so."""
    grupos = {}
    for midia in fotos:
        url = vinculos.url_publica(enviador.configuracao, midia.url)
        if not url:
            raise ShopifyErro("Fotos nao reenviadas: o hub nao tem endereco publico. Preencha "
                              "a URL dos webhooks na integracao e sincronize de novo.")
        grupos.setdefault(url, []).append(midia)
    return list(grupos.items())


def _esperar(cliente, ids):
    """{id: CDN} das prontas."""
    prontas = {}
    for tentativa in range(TENTATIVAS):
        if tentativa:
            time.sleep(ESPERA)
        prontas = vinculos.cdn_por_id(cliente, ids)
        if len(prontas) == len(ids):
            break
    return prontas


def _marcar(produto, ids):
    """Antes do fileDelete: webhook atrasado nao traz a foto de volta nem apaga a linha."""
    for vinculo in vinculos.referencias(produto.account_id).filter(external_id__in=ids):
        vinculo.object_id, vinculo.metadata = "", {**(vinculo.metadata or {}), MARCA: True}
        vinculo.save(update_fields=["object_id", "metadata", "updated_at"])


def _apagar(enviador, produto, ids):
    if not ids:
        return
    _marcar(produto, ids)
    enviador.mutacao(midias_shopify.APAGAR, {"fileIds": sorted(ids)}, "fileDelete")
    for vinculo in vinculos.referencias(produto.account_id).filter(external_id__in=ids):
        vinculo.metadata = {**vinculo.metadata, "removida_da_loja": True}
        vinculo.save(update_fields=["metadata", "updated_at"])


def refazer(enviador, produto, produto_gid):
    fotos = midias_shopify.fotos_do_hub(produto)
    antigas = ids_na_loja(enviador.cliente, produto_gid)
    if antigas is None:
        return
    antigas = {i for i in antigas if i.startswith("gid://shopify/MediaImage/")}
    if not fotos:
        if antigas:
            avisar("Fotos da loja mantidas: o produto nao tem foto no hub.",
                   recurso="produtos", id=str(produto.pk), descricao=produto.nome)
        return
    grupos = _grupos(enviador, fotos)
    if len(antigas) + len(grupos) > MAXIMO:
        raise ShopifyErro(f"Fotos nao reenviadas: {len(antigas)} na loja e {len(grupos)} no "
                          f"hub passam de {MAXIMO}, o maximo do Shopify. Apague as repetidas "
                          "na loja e sincronize de novo.")
    resposta = enviador.mutacao(ACRESCENTAR, {
        "product": {"id": produto_gid}, "media": midias_shopify.novas(grupos)}, "productUpdate")
    nos = ((resposta.get("product") or {}).get("media") or {}).get("nodes") or []
    novas = [n["id"] for n in nos if n["id"] not in antigas][-len(grupos):]
    # O vinculo novo vem ja: o webhook deste update chega enquanto as fotos processam.
    for externo, (url, midias) in zip(novas, grupos, strict=False):
        vinculos.vincular(midias[0], externo, {"enviado_src": url}, produto_gid)
    prontas = _esperar(enviador.cliente, novas)
    if len(novas) < len(grupos) or len(prontas) < len(grupos):
        _apagar(enviador, produto, set(novas))
        raise ShopifyErro("Fotos nao reenviadas: o Shopify nao processou "
                          f"{len(grupos) - len(prontas)} de {len(grupos)}; as da loja foram "
                          "mantidas. Confira se a URL publica do hub abre as fotos e "
                          "sincronize de novo.")
    for vinculo in vinculos.referencias(produto.account_id).filter(external_id__in=novas):
        vinculos.gravar_cdn(vinculo, prontas[vinculo.external_id])
    _apagar(enviador, produto, antigas)
