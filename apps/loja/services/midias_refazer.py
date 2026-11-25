"""Galeria do zero: apaga as fotos do produto e grava as que vieram da loja.

So no Sincronizar > Importar. Webhook e edicao seguem pela referencia.

    fotos = [{"variante": v, "src": "/media/nova.png", "alt": "", "posicao": 0,
              "externo": "gid://...", "metadata": {...}}]
    refazer(produto, fotos, "shopify")

Chame com as fotos JA baixadas: foto que nao baixou nao pode custar a galeria. Nenhum
arquivo antigo e apagado do MEDIA; baixada igual (mesmos bytes) a uma antiga usa o arquivo
antigo e a copia recem-baixada e descartada, senao cada sincronizacao dobrava o disco.
"""

from django.core.files.storage import default_storage
from django.db import transaction

from apps.core.imagens_iguais import identidade, nome_no_media
from apps.core.models import ExternalReference
from apps.loja.models import MidiaProduto, Produto

ENTIDADE = "midias"


def _descartar(url):
    if nome := nome_no_media(url):
        default_storage.delete(nome)


def _reaproveitar(fotos, antigas):
    """Troca o `src` da foto igual a uma antiga (ou a outra nova) pelo arquivo que ja existe."""
    guardadas = {identidade(m.url): m.url for m in reversed(antigas)}
    em_uso = {m.url for m in antigas}
    for foto in fotos:
        url = guardadas.setdefault(identidade(foto["src"]), foto["src"])
        if url != foto["src"]:
            if foto["src"] not in em_uso:
                _descartar(foto["src"])
            foto["src"] = url


def _criar(produto, fotos, plataforma):
    linhas = {}
    for foto in fotos:
        chave = (foto["variante"].pk, foto["src"])
        # A mesma foto duas vezes na loja e uma linha so (com os dois vinculos).
        linhas[chave] = linhas.get(chave) or MidiaProduto.objects.create(
            produto=produto, variante=foto["variante"], url=foto["src"],
            alt_text=foto["alt"][:255], posicao=foto["posicao"], origin=plataforma)
        foto["midia"] = linhas[chave]
    return list(linhas.values())


def _vinculos(conta_id, **filtro):
    return ExternalReference.all_objects.filter(account_id=conta_id, entity_type=ENTIDADE,
                                                **filtro)


def _herdar(antigas, novas, plataforma):
    """Vinculos da loja importada saem (nascem de novo); os das outras passam para a linha
    nova da mesma foto, senao o proximo envio a mandaria outra vez para la."""
    por_url = {m.url: m for m in reversed(novas)}
    for midia in antigas:
        seus = _vinculos(midia.account_id, object_id=str(midia.pk))
        seus.filter(platform=plataforma).delete()
        if midia.url in por_url:
            seus.update(object_id=str(por_url[midia.url].pk))


def refazer(produto, fotos, plataforma):
    if not fotos:
        return  # loja sem foto: apagar deixaria o produto sem nenhuma
    with transaction.atomic():
        Produto.all_objects.select_for_update().filter(pk=produto.pk).first()
        antigas = list(produto.midias.filter(tipo=MidiaProduto.Tipo.IMAGEM)
                       .order_by("posicao", "pk"))
        _reaproveitar(fotos, antigas)
        novas = _criar(produto, fotos, plataforma)
        _herdar(antigas, novas, plataforma)
        MidiaProduto.objects.filter(pk__in=[m.pk for m in antigas]).delete()
        feitos = set()
        for foto in fotos:
            # Foto em varias variacoes: um vinculo, na primeira. A chave e o id externo
            # (indice unico); a marca de "apagada no hub" sai: a loja mandou de novo.
            if foto["externo"] and foto["externo"] not in feitos:
                feitos.add(foto["externo"])
                ExternalReference.all_objects.update_or_create(
                    account_id=produto.account_id, platform=plataforma, entity_type=ENTIDADE,
                    external_id=str(foto["externo"]),
                    defaults={"object_id": str(foto["midia"].pk), "origin": plataforma,
                              "metadata": foto["metadata"]})
