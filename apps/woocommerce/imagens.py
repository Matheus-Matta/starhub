"""Imagens do produto da loja WooCommerce baixadas para o MEDIA do hub.

    lista = imagens_locais(produto, [{"id": 31, "src": "https://loja/foto.jpg", "alt": ""}])
    sincronizar_midias(variante, lista)

A imagem ja baixada e reconhecida pelo vinculo "midias" (id da imagem no Woo +
src): sincronizar de novo nao baixa nem duplica. O download (so http(s) publico)
e o de apps/core/imagens_remotas.py. Foto que nao baixa vira aviso na tarefa e o
produto segue.
"""

from apps.core.imagens_iguais import mesmo_arquivo
from apps.core.imagens_remotas import ImagemErro, baixar
from apps.core.models import Origin
from apps.loja.models import MidiaProduto, VarianteProduto
from apps.loja.services.midias import url_da_foto
from apps.loja.services.midias_refazer import refazer as refazer_galeria
from apps.woocommerce import vinculos
from apps.woocommerce.contexto import avisar

__all__ = ["ImagemErro", "baixar", "imagens_locais", "refazer", "vincular_midias"]


def imagens_locais(produto, imagens):
    """[{"id" (midia do hub ou None), "src" local, "alt", "_woo_id"}] na ordem da loja."""
    lista = []
    for imagem in imagens or []:
        woo_id, url = imagem.get("id"), imagem.get("src") or ""
        if not url:
            continue
        midia = vinculos.existente("midias", MidiaProduto, woo_id) if woo_id else None
        if midia is not None and midia.produto_id == produto.pk:
            lista.append({"id": midia.pk, "src": midia.url, "alt": imagem.get("alt") or "",
                          "_woo_id": woo_id})
            continue
        try:
            local = url_da_foto(produto, baixar(url), lista)
        except ImagemErro as erro:
            avisar(f"Imagem nao importada: {erro}", recurso="produtos", id=produto.pk,
                   descricao=produto.nome, id_externo=woo_id or "")
            continue
        lista.append({"id": None, "src": local, "alt": imagem.get("alt") or "",
                      "_woo_id": woo_id})
    return lista


def vincular_midias(variante, lista):
    """Depois do sincronizar_midias: liga cada midia nova ao id da imagem no Woo."""
    # Pela url, e nao pela ordem: foto repetida na loja e uma linha so no hub.
    por_url = {mesmo_arquivo(m.url): m for m in variante.midias.all()}
    for item in lista:
        midia = por_url.get(mesmo_arquivo(item["src"]))
        if item.get("_woo_id") and midia:
            vinculos.referenciar("midias", item["_woo_id"], midia,
                                 metadata={"src": item["src"]})


def _da_loja(produto, dados, variacoes):
    """{id da imagem: (imagem, [variantes])}; imagem sem variacao vai para a padrao."""
    padrao = produto.variantes.filter(is_default=True).first() or produto.variantes.first()
    fotos = {i["id"]: (i, []) for i in dados.get("images") or [] if i.get("id") and i.get("src")}
    for variacao in variacoes or ():
        imagem = variacao.get("image") or {}
        variante = vinculos.existente("variantes", VarianteProduto, variacao["id"])
        if imagem.get("id") and imagem.get("src") and variante is not None \
                and variante.produto_id == produto.pk:
            fotos.setdefault(imagem["id"], (imagem, []))[1].append(variante)
    return [(imagem, variantes or [padrao]) for imagem, variantes in fotos.values()]


def refazer(produto, dados, variacoes):
    """Sincronizar > Importar: saem as fotos do hub, entram as do WooCommerce."""
    fotos = []
    try:
        for posicao, (imagem, variantes) in enumerate(_da_loja(produto, dados, variacoes)):
            src = baixar(imagem["src"])
            fotos += [{"variante": v, "src": src, "alt": imagem.get("alt") or "",
                       "posicao": posicao, "externo": imagem["id"],
                       "metadata": {"src": imagem["src"]}} for v in variantes]
    except ImagemErro as erro:
        avisar(f"Imagem nao importada: {erro} As fotos do hub foram mantidas.",
               recurso="produtos", id=produto.pk, descricao=produto.nome,
               id_externo=dados.get("id") or "")
        return
    refazer_galeria(produto, fotos, Origin.WOOCOMMERCE)
