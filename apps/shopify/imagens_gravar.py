"""Grava no hub a foto que veio da loja: a nova (`nova`) e a ja ligada (`conhecida`).

Os dois travam o produto so para gravar, e releem a galeria depois da trava: dois webhooks
do mesmo produto (ou o webhook e o envio que o criou) rodam ao mesmo tempo.
"""

from django.db import transaction

from apps.core.imagens_iguais import url_ja_guardada
from apps.core.models import ExternalReference, Origin
from apps.loja.models import MidiaProduto, Produto
from apps.shopify import midias as vinculos
from apps.shopify import midias_apagadas
from apps.shopify.imagens_baixar import _baixar


def variantes_por_gid(produto, gids):
    referencias = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type="variantes", external_id__in=gids)
    return list(produto.variantes.filter(pk__in=[r.object_id for r in referencias]))


def _variantes(produto, ids):
    return variantes_por_gid(produto, ids) or (
        [produto.variante_padrao] if produto.variante_padrao else [])


def _copias(produto, url):
    """Uma linha por variante, todas com o mesmo arquivo."""
    return list(produto.midias.filter(url=url).order_by("pk"))


def _linhas(produto, imagem, copias, campos):
    """Acerta as copias com os `campos` e cria a que falta nas variantes da foto."""
    ids = imagem.get("variantIds") or imagem.get("variant_ids") or []
    if ids or not copias:
        com_foto = {m.variante_id for m in copias}
        copias = copias + [MidiaProduto(produto=produto, variante=v, origin=Origin.SHOPIFY)
                           for v in _variantes(produto, ids) if v.pk not in com_foto]
    for midia in copias:
        novos = {**campos} if midia.pk else {"url": copias[0].url, "alt_text":
                                             copias[0].alt_text, **campos}
        if midia.pk and all(getattr(midia, c) == v for c, v in novos.items()):
            continue
        for campo, valor in novos.items():
            setattr(midia, campo, valor)
        midia.save()
    return copias


def conhecida(produto, imagem, vinculo, midias, externo_id, url, alt, posicao):
    """Ja ligada: so o que a LOJA mudou desde a ultima vez vem para o hub."""
    meta = vinculo.metadata or {}
    visto = {"alt_text": alt, "posicao": posicao}
    antes = meta.get("visto") or visto  # vinculo antigo: so anota
    campos = {c: v for c, v in visto.items() if antes.get(c) != v}
    anterior, base = meta.get("shopify_src"), midias[vinculo.object_id]
    if not anterior or vinculos.sem_versao(anterior) != vinculos.sem_versao(url):
        campos["url"] = _baixar(url)
    with transaction.atomic():
        Produto.all_objects.select_for_update().filter(pk=produto.pk).first()
        copias = _copias(produto, base.url)
        if not copias:
            return  # apagada no hub enquanto a foto baixava
        _linhas(produto, imagem, copias, campos)
        novo = {"shopify_src": url, "visto": visto}
        if (vinculo.external_id, meta) != (externo_id, novo):
            vinculo.external_id, vinculo.metadata = externo_id, novo
            vinculo.save(update_fields=["external_id", "metadata", "updated_at"])


def nova(produto, imagem, externo_id, url, alt, posicao):
    # O download fica fora da transacao: a trava do produto dura so a gravacao.
    url_local = _baixar(url)
    with transaction.atomic():
        # Outro webhook (ou o envio que criou o produto) gravava a mesma foto ao mesmo
        # tempo. Este espera a trava e confere o vinculo de novo.
        Produto.all_objects.select_for_update().filter(pk=produto.pk).first()
        existente = vinculos.referencias(produto.account_id).filter(
            external_id=externo_id).first()
        if existente and (midias_apagadas.MARCA in (existente.metadata or {})
                          or produto.midias.filter(pk=existente.object_id).exists()):
            return
        atuais = produto.midias.order_by("pk").values_list("url", flat=True)
        igual = url_ja_guardada(url_local, atuais)
        campos = {} if igual else {"url": url_local, "alt_text": alt, "posicao": posicao}
        linhas = _linhas(produto, imagem, _copias(produto, igual) if igual else [], campos)
        if linhas:
            vinculos.vincular(linhas[0], externo_id, {
                "shopify_src": url, "visto": {"alt_text": alt, "posicao": posicao}})
