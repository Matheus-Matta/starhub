"""Imagens do produto da loja WooCommerce baixadas para o MEDIA do hub.

    lista = imagens_locais(produto, [{"id": 31, "src": "https://loja/foto.jpg", "alt": ""}])
    sincronizar_midias(variante, lista)

A imagem ja baixada e reconhecida pelo vinculo "midias" (id da imagem no Woo +
src): sincronizar de novo nao baixa nem duplica. O download (so http(s) publico)
e o de apps/core/imagens_remotas.py. Foto que nao baixa vira aviso na tarefa e o
produto segue.
"""

from apps.core.imagens_remotas import ImagemErro, baixar
from apps.loja.models import MidiaProduto
from apps.woocommerce import vinculos
from apps.woocommerce.contexto import avisar

__all__ = ["ImagemErro", "baixar", "imagens_locais", "vincular_midias"]


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
            local = baixar(url)
        except ImagemErro as erro:
            avisar(f"Imagem nao importada: {erro}", recurso="produtos", id=produto.pk,
                   descricao=produto.nome, id_externo=woo_id or "")
            continue
        lista.append({"id": None, "src": local, "alt": imagem.get("alt") or "",
                      "_woo_id": woo_id})
    return lista


def vincular_midias(variante, lista):
    """Depois do sincronizar_midias: liga cada midia nova ao id da imagem no Woo."""
    midias = list(variante.midias.order_by("posicao", "id"))
    for midia, item in zip(midias, lista, strict=False):
        if item.get("_woo_id"):
            vinculos.referenciar("midias", item["_woo_id"], midia,
                                 metadata={"src": item["src"]})
