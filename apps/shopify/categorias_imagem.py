"""Imagem da categoria entre hub e Shopify, registrada no vinculo da colecao.

metadata do ExternalReference "categorias" (platform shopify), nunca na Categoria:
- "imagem_enviada": `imagem.src` do hub mandada na ultima vez;
- "imagem_shopify": URL da CDN que a loja devolveu por ultimo;
- "imagem_origem": URL da CDN (sem `?v=`) da foto que o hub baixou para o MEDIA;
- "imagem_local": `imagem.src` local que esse download gerou.

O Shopify rehospeda a foto com outra URL. Sem este registro o hub mandava a mesma
foto a cada update, e o webhook de volta trocava a URL do hub pela da CDN.
A foto que vem da loja e baixada para o MEDIA (como as fotos de produto): o hub
nao depende da CDN para mostrar a propria categoria.
"""

import logging

from apps.core.models import ExternalReference, Origin
from apps.shopify.contexto import avisar
from apps.shopify.imagens import ImagemShopifyErro, _baixar
from apps.shopify.midias import sem_versao

logger = logging.getLogger(__name__)
DO_DOWNLOAD = ("imagem_origem", "imagem_local")


def _url(imagem):
    imagem = imagem if isinstance(imagem, dict) else {}
    return imagem.get("url") or imagem.get("src") or ""


def ja_na_loja(registro, src):
    """A loja ja tem esta foto: foi enviada, e a CDN dela ou foi baixada dela."""
    if registro is None or not src:
        return False
    meta = registro.metadata or {}
    return src in (meta.get("imagem_enviada"), meta.get("imagem_shopify"),
                   meta.get("imagem_local"))


def _gravar(registro, meta):
    if registro is not None and meta != (registro.metadata or {}):
        registro.metadata = meta
        registro.save(update_fields=["metadata", "updated_at"])


def registrar_envio(registro, src):
    if registro is None:
        return
    # A foto do hub passou a ser outra: o download antigo nao descreve mais a loja.
    fora = ("imagem_shopify", *DO_DOWNLOAD)
    meta = {k: v for k, v in (registro.metadata or {}).items() if k not in fora}
    _gravar(registro, {**meta, "imagem_enviada": src})


def registro_de(categoria):
    return ExternalReference.all_objects.filter(
        account_id=categoria.account_id, platform=Origin.SHOPIFY,
        entity_type="categorias", object_id=str(categoria.pk),
    ).first()


def registrar_importada(categoria, imagem):
    """Categoria do hub vinculada pela importacao: a CDN atual ja e da loja (nao reenviar)."""
    registro, url = registro_de(categoria), _url(imagem)
    if registro is not None and url:
        _gravar(registro, {**(registro.metadata or {}), "imagem_shopify": url})


def _baixada(url, imagem, categoria=None):
    """Copia local da foto da loja no formato do hub, ou None se o download falhou.

    Falha no download nao derruba a categoria: fica no log e na mensagem da execucao,
    e o vinculo nao registra a origem, entao a proxima sincronizacao tenta de novo.
    """
    try:
        local = _baixar(url, pasta="categorias")
    except ImagemShopifyErro as erro:
        logger.warning("Imagem da colecao nao baixada (%s): %s", url, erro)
        avisar(f"Imagem da colecao nao baixada ({url}): {erro}. "
               "Sincronize as categorias de novo para tentar outra vez.",
               recurso="categorias", id=getattr(categoria, "pk", ""),
               descricao=getattr(categoria, "nome", ""),
               id_externo=getattr(registro_de(categoria), "external_id", "") if categoria else "")
        return None
    return {"src": local, "alt": imagem.get("altText") or imagem.get("alt") or ""}


def _eco(meta, atual):
    # Primeira CDN depois do envio (registrar_envio limpa "imagem_shopify") com o hub
    # ainda na foto enviada: e o eco da foto do hub, que fica com a URL dele.
    return bool(meta.get("imagem_enviada") and not meta.get("imagem_shopify")
                and atual.get("src") == meta["imagem_enviada"])


def recebida(categoria, imagem):
    """Imagem que a categoria do hub fica depois da importacao/webhook da colecao."""
    url = _url(imagem)
    registro = registro_de(categoria)
    meta = dict((registro.metadata if registro else None) or {})
    atual = categoria.imagem if isinstance(categoria.imagem, dict) else {}
    if not url:
        # Decisao: colecao sem imagem na loja nao apaga a foto do hub (pode ter sido
        # cadastrada so no hub); tirar a imagem e feito no proprio hub.
        return categoria.imagem
    if sem_versao(url) in (sem_versao(meta.get("imagem_shopify")), meta.get("imagem_origem")):
        # A foto da loja nao mudou (so o ?v= da CDN): nada novo para o hub.
        _gravar(registro, {**meta, "imagem_shopify": url})
        return categoria.imagem
    if _eco(meta, atual):
        _gravar(registro, {**meta, "imagem_shopify": url})
        return categoria.imagem
    nova = _baixada(url, imagem, categoria)
    if nova is None:
        return categoria.imagem
    meta = {k: v for k, v in meta.items() if k != "imagem_enviada"}
    _gravar(registro, {**meta, "imagem_shopify": url, "imagem_origem": sem_versao(url),
                       "imagem_local": nova["src"]})
    return nova
