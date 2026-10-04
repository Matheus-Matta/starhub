"""Imagens do produto do hub -> midias do Shopify, sem mandar a mesma URL duas vezes.

Create: `files` do productSet ("The files to associate with the product.").
Update: `media` do productUpdate ("List of new media to be added to the product."):
so acrescenta, nunca apaga midia da loja. productCreateMedia esta deprecado na
2026-07 ("Deprecated. Use productUpdate or productSet instead.").

Midia com vinculo "midias" ja esta na loja (enviada pelo hub ou importada dela) e
nao vai de novo; URL ja enviada tambem nao (a mesma foto ligada a outra variante e
outra linha no hub, mas e uma midia so no Shopify).
"""

import logging

from apps.loja.models import MidiaProduto
from apps.shopify import midias as vinculos
from apps.shopify.cliente import ShopifyErro

logger = logging.getLogger(__name__)


def pendentes(enviador, produto):
    """[(url publica, [midias com essa URL])] que ainda nao estao no Shopify."""
    todas = list(produto.midias.filter(tipo=MidiaProduto.Tipo.IMAGEM).order_by("posicao", "id"))
    ligadas = {r.object_id: r for r in vinculos.do_produto(produto, todas)}
    na_loja = set()
    for midia in todas:
        referencia = ligadas.get(str(midia.pk))
        if referencia:
            na_loja.update({midia.url, referencia.metadata.get("enviado_src")})
    grupos = {}
    for midia in todas:
        url = vinculos.url_publica(enviador.configuracao, midia.url)
        if str(midia.pk) in ligadas or not url or {url, midia.url} & na_loja:
            continue
        grupos.setdefault(url, []).append(midia)
    return list(grupos.items())


def arquivos(grupos):
    """FileSetInput do productSet."""
    return [{"originalSource": url, "alt": midias[0].alt_text, "contentType": "IMAGE"}
            for url, midias in grupos]


def novas(grupos):
    """CreateMediaInput do productUpdate."""
    return [{"originalSource": url, "alt": midias[0].alt_text, "mediaContentType": "IMAGE"}
            for url, midias in grupos]


def registrar(enviador, grupos, recebidas, produto_gid):
    """Grava o vinculo de cada grupo com o id da midia criada na loja e, se ja
    estiver pronta, a URL da CDN (o webhook de volta casa sem consultar a loja).

    `recebidas` sao as midias criadas, na ordem da entrada. Sem o id (resposta sem
    a midia), o vinculo fica "pendente:<pk>" com a URL enviada: basta para nao
    reenviar, mas a importacao nao tem como reconhecer o eco dessa foto.
    """
    criados = []
    for posicao, (url, midias) in enumerate(grupos):
        recebida = recebidas[posicao] if posicao < len(recebidas) else {}
        external_id = recebida.get("id") or f"{vinculos.PENDENTE}{midias[0].pk}"
        criados.append(vinculos.vincular(midias[0], external_id, {"enviado_src": url},
                                         produto_gid))
    # Midia ainda em PROCESSING fica sem CDN: a importacao pergunta de novo (imagens.py).
    # Erro aqui nao derruba o envio: no create o produto ja existe na loja e, sem o
    # vinculo gravado pela base, a nova tentativa criaria o produto duplicado.
    try:
        prontas = vinculos.cdn_por_id(enviador.cliente, [v.external_id for v in criados])
    except ShopifyErro as erro:
        logger.warning("Midias enviadas sem confirmar a CDN (%s); a importacao confirma.", erro)
        return
    for vinculo in criados:
        if vinculo.external_id in prontas:
            vinculos.gravar_cdn(vinculo, prontas[vinculo.external_id])
