"""Imagens do produto do hub -> midias do Shopify, sem mandar a mesma URL duas vezes.

Create: `files` do productSet ("The files to associate with the product.").
Update: `media` do productUpdate ("List of new media to be added to the product.")
acrescenta as novas; depois sai da loja (fileDelete) a midia com vinculo cuja foto
foi apagada no hub ou trocada (mesma linha, URL nova: vai a nova, sai a antiga).
Midia da loja sem vinculo (cadastrada direto la) nunca e apagada. productCreateMedia
esta deprecado na 2026-07 ("Deprecated. Use productUpdate or productSet instead.").

Midia com vinculo "midias" ja esta na loja (enviada pelo hub ou importada dela) e
nao vai de novo; URL ja enviada tambem nao (a mesma foto ligada a outra variante e
outra linha no hub, mas e uma midia so no Shopify).
"""

import logging

from apps.loja.models import MidiaProduto
from apps.shopify import midias as vinculos
from apps.shopify.cliente import ShopifyErro
from apps.shopify.envio import produtos_midias_reserva as reserva
from apps.shopify.midias_apagadas import MARCA

logger = logging.getLogger(__name__)


APAGAR = """mutation($fileIds: [ID!]!) {
  fileDelete(fileIds: $fileIds) { deletedFileIds userErrors { field message code } }
}"""


def fotos_do_hub(produto):
    return list(produto.midias.filter(tipo=MidiaProduto.Tipo.IMAGEM).order_by("posicao", "id"))


def _trocada(enviador, midia, vinculo):
    """Foto que nasceu no hub e cuja URL mudou depois do envio (a importada nao tem
    `enviado_src`: a URL do hub dela nunca foi a da loja)."""
    enviado = (vinculo.metadata or {}).get("enviado_src")
    return bool(enviado) and enviado not in {
        midia.url, vinculos.url_publica(enviador.configuracao, midia.url)}


def trocadas(enviador, produto):
    """Vinculos das fotos trocadas no hub: a midia antiga sai da loja."""
    todas = {str(m.pk): m for m in fotos_do_hub(produto)}
    return [v for v in vinculos.do_produto(produto, todas.values())
            if _trocada(enviador, todas[v.object_id], v)]


def pendentes(enviador, produto):
    """[(url publica, [midias com essa URL])] que ainda nao estao no Shopify."""
    todas = fotos_do_hub(produto)
    velhas = {v.pk for v in trocadas(enviador, produto)}
    ligadas = {r.object_id: r for r in vinculos.do_produto(produto, todas)
                if r.pk not in velhas and not reserva.vencida(r)}
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
        reserva.devolver(midias[:1])
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


def remover(enviador, produto, na_loja, velhas):
    """Apaga da loja as midias do produto (`na_loja`: ids da resposta do productUpdate)
    cuja foto saiu do hub, e as `velhas` (trocadas). So midia com vinculo."""
    existentes = {str(pk) for pk in produto.midias.values_list("pk", flat=True)}
    ids = set(na_loja)
    saem = [v for v in vinculos.referencias(produto.account_id).filter(external_id__in=ids)
            if v.object_id not in existentes and not (v.metadata or {}).get("removida_da_loja")]
    saem += [v for v in velhas if v.external_id in ids]
    if not saem:
        return
    gids = list(dict.fromkeys(v.external_id for v in saem))
    enviador.mutacao(APAGAR, {"fileIds": gids}, "fileDelete")
    # O vinculo fica, marcado: webhook de antes do fileDelete ainda traz a foto. Sem a
    # linha, ele nao apaga de novo nem deixa a importacao baixar.
    for vinculo in saem:
        vinculo.metadata = {**(vinculo.metadata or {}), MARCA: True, "removida_da_loja": True}
        vinculo.object_id = ""
        vinculo.save(update_fields=["object_id", "metadata", "updated_at"])
