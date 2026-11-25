"""Foto apagada de um lado sai do outro, sem voltar por um webhook atrasado.

O vinculo "midias" e a memoria do que hub e loja ja combinaram. Com ele:

    linha no hub | vinculo | na loja | o que e
    sim          | nao     | nao     | nova no hub: o envio manda
    nao          | nao     | sim     | nova na loja: a importacao baixa
    nao          | sim     | sim     | APAGADA NO HUB: o envio apaga la (produtos_midias)
    sim          | sim     | nao     | APAGADA NA LOJA: a importacao apaga aqui

Apagada no hub: o vinculo fica marcado (`apagada_no_hub`) e nunca mais e importado. O
webhook do proprio update chega antes do fileDelete, ainda com a foto na lista, e a
baixava de novo.

Apagada na loja: o webhook pode ser velho (de antes de o hub mandar a foto). So sai a
que a loja, perguntada de novo, confirma que nao tem mais; e so a que ja foi vista pronta
la (`shopify_src`), porque a que falhou no envio existe so no hub. Sai a linha da galeria,
o arquivo fica no MEDIA. A linha some junto com o vinculo: nada volta para a loja.
"""

from django.db import transaction
from django.db.models.signals import post_delete

from apps.core.models import ExternalReference, Origin
from apps.loja.models import MidiaProduto, Produto
from apps.shopify import midias as vinculos

MARCA = "apagada_no_hub"
# Custo: produto 1 + conexao 3 + 250 fotos = 254.
NA_LOJA = """query($id: ID!) { product(id: $id) { fotosAgora: media(first: 250) {
  nodes { id } } } }"""


def _ao_apagar(sender, instance, origin=None, **kwargs):
    """Depois de apagar a linha: a copia da mesma foto em outra variacao herda o vinculo
    (a foto segue na loja); sem copia, o vinculo e marcado. Produto inteiro excluido nao
    marca: se a loja o mantiver, importar de novo tem que trazer as fotos."""
    if isinstance(origin, Produto) or getattr(origin, "model", None) is Produto:
        return
    copia = MidiaProduto.all_objects.filter(
        produto_id=instance.produto_id, url=instance.url).order_by("posicao", "pk").first()
    for vinculo in vinculos.referencias(instance.account_id).filter(
            object_id=str(instance.pk)):
        if copia is not None:
            vinculo.object_id = str(copia.pk)
        else:
            vinculo.metadata = {**(vinculo.metadata or {}), MARCA: True}
        vinculo.save(update_fields=["object_id", "metadata", "updated_at"])


def conectar():
    post_delete.connect(_ao_apagar, sender=MidiaProduto, dispatch_uid="shopify-midia-apagada")


def apagadas_no_hub(produto, ids):
    """Dos ids da loja, os que o operador apagou no hub."""
    return set(vinculos.referencias(produto.account_id).filter(
        external_id__in=ids, metadata__apagada_no_hub=True
    ).values_list("external_id", flat=True))


def ids_na_loja(cliente, produto_gid):
    """Fotos do produto na loja agora; None sem loja no contexto ou produto que sumiu."""
    if cliente is None or not produto_gid:
        return None
    produto = (cliente.graphql(NA_LOJA, {"id": produto_gid}) or {}).get("product") or {}
    if "fotosAgora" not in produto:
        return None
    return {n["id"] for n in produto["fotosAgora"].get("nodes") or [] if n}


def candidatas(produto, produto_gid, lista, recebidas):
    """Vinculos que a loja ja teve e que nao vieram na lista recebida."""
    ids = list(ExternalReference.all_objects.filter(
        account_id=produto.account_id, platform=Origin.SHOPIFY, entity_type="produtos",
        object_id=str(produto.pk)).values_list("external_id", flat=True))
    if ids != [produto_gid]:
        return []  # ligado a mais de um produto da loja: a lista de um nao tem a do outro
    return [v for v in lista if v.external_id.startswith("gid://shopify/MediaImage/")
            and v.external_id not in recebidas and (v.metadata or {}).get("shopify_src")]


def tirar_do_hub(produto, vinculos_que_sairam):
    with transaction.atomic():
        Produto.all_objects.select_for_update().filter(pk=produto.pk).first()
        for antigo in vinculos_que_sairam:
            # Relido depois da trava: outro webhook pode ter acabado de tirar ou religar.
            vinculo = vinculos.referencias(produto.account_id).filter(
                pk=antigo.pk, external_id=antigo.external_id).first()
            midia = (produto.midias.filter(pk=vinculo.object_id).first()
                     if vinculo is not None else None)
            if midia is None:
                continue
            vinculo.delete()
            copias = list(produto.midias.filter(url=midia.url))
            # A loja tinha a mesma foto duas vezes e apagou uma: a outra segue valendo.
            if not vinculos.do_produto(produto, copias):
                MidiaProduto.objects.filter(pk__in=[m.pk for m in copias]).delete()
