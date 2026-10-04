"""Importa as imagens do produto do Shopify para o MEDIA do StarHub, sem duplicar.

Antes de baixar, a imagem e reconhecida pelo vinculo "midias" (apps/shopify/midias.py):
a) a URL da CDN e a mesma da ultima importacao (`shopify_src`), sem o `?v=`: a
   consulta GraphQL e o webhook devolvem o mesmo arquivo com versoes diferentes;
b) o id e o do vinculo (a MediaImage do envio) ou o `imagem_id` visto antes;
c) a URL de origem e a propria URL que o hub enviou (`enviado_src`);
d) nada bateu e ha foto enviada ainda sem CDN (estava em PROCESSING no envio):
   pergunta a loja a URL da CDN dessas midias pelo id do vinculo e compara.
So baixa se nada bater. Texto alternativo nunca identifica: uma foto que falhou na
loja faria o hub adotar outra foto cadastrada la no lugar dela. Foto que nasceu no
hub continua com a URL do hub: o eco so completa o vinculo com a CDN.
"""

import urllib.request
from pathlib import PurePath
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from django.core.files.base import ContentFile

from apps.core.imagens import TAMANHO_MAXIMO, salvar
from apps.core.models import ExternalReference, Origin
from apps.loja.models import MidiaProduto
from apps.shopify import midias as vinculos
from apps.shopify.contexto import avisar

HOSTS_SHOPIFY = {"cdn.shopify.com", "cdn.shopifycdn.net"}


class ImagemShopifyErro(RuntimeError):
    pass


# Foto maior que 5 MB (PNG de ambiente da loja) vem reduzida pela propria CDN da
# Shopify (`width=`): 2048 px sobra para a vitrine e cabe no limite do hub.
LARGURAS = (2048, 1600, 1200)


def _com_largura(url, largura):
    partes = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(partes.query) if k != "width"] + [("width", largura)]
    return urlunsplit(partes._replace(query=urlencode(query)))


def _ler(url, nome, timeout):
    """Bytes da imagem, ou None se passa de 5 MB."""
    requisicao = urllib.request.Request(url, headers={"User-Agent": "StarHub/1.0"})
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            if int(resposta.headers.get("Content-Length") or 0) > TAMANHO_MAXIMO:
                return None
            conteudo = resposta.read(TAMANHO_MAXIMO + 1)
    except (HTTPError, URLError, TimeoutError, ValueError) as erro:
        raise ImagemShopifyErro(f"Nao foi possivel baixar {nome}: {erro}") from erro
    return conteudo if len(conteudo) <= TAMANHO_MAXIMO else None


def _baixar(url, timeout=20, pasta="produtos"):
    partes = urlsplit(url)
    if partes.scheme != "https" or partes.hostname not in HOSTS_SHOPIFY:
        raise ImagemShopifyErro("A imagem nao pertence ao CDN HTTPS da Shopify.")
    nome = PurePath(unquote(partes.path)).name or "imagem"
    for tentativa in (url, *(_com_largura(url, largura) for largura in LARGURAS)):
        conteudo = _ler(tentativa, nome, timeout)
        if conteudo is not None:
            item = salvar(ContentFile(conteudo, name=nome), pasta)
            return item["src"]
    raise ImagemShopifyErro(
        f"{nome}: passa de 5 MB mesmo reduzida a {LARGURAS[-1]} px; "
        "diminua a foto na loja e sincronize de novo."
    )


def _variantes(produto, ids):
    referencias = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY,
        entity_type="variantes",
        external_id__in=ids,
    )
    variantes = list(produto.variantes.filter(
        pk__in=[referencia.object_id for referencia in referencias]
    ))
    return variantes or ([produto.variante_padrao] if produto.variante_padrao else [])


def _mesma(vinculo, externo_id, url):
    meta = vinculo.metadata or {}
    return (
        url == meta.get("enviado_src")
        or (meta.get("shopify_src")
            and vinculos.sem_versao(url) == vinculos.sem_versao(meta["shopify_src"]))
        or externo_id in (vinculo.external_id, meta.get("imagem_id"))
    )


class _Loja:
    """Consulta a CDN das fotos enviadas ainda sem CDN, uma vez por importacao."""

    def __init__(self, lista):
        self.lista, self.cdn = lista, None

    def reconhecer(self, externo_id, url):
        vinculo = next((v for v in self.lista if _mesma(v, externo_id, url)), None)
        if vinculo or not vinculos.sem_cdn(self.lista):
            return vinculo
        if self.cdn is None:
            # Erro da loja sobe: a execucao falha e e reprocessada, em vez de baixar
            # uma copia da foto que talvez seja a do proprio hub.
            ids = [v.external_id for v in vinculos.sem_cdn(self.lista)]
            self.cdn = vinculos.cdn_por_id(vinculos.cliente_da_loja(), ids)
        alvo = vinculos.sem_versao(url)
        return next((v for v in vinculos.sem_cdn(self.lista)
                     if vinculos.sem_versao(self.cdn.get(v.external_id)) == alvo
                     and self.cdn.get(v.external_id)), None)


def _da_consulta(media):
    """`media` da GraphQL no formato das imagens do webhook (id, src, alt).

    So a MediaImage pronta tem `image`: video, modelo 3D e foto em PROCESSING
    ficam de fora (a foto chega pronta no proximo webhook/sincronizacao).
    """
    imagens = []
    for node in media.get("nodes") or []:
        imagem = (node or {}).get("image") or {}
        if imagem.get("url"):
            imagens.append({"id": node["id"], "src": imagem["url"],
                            "alt": node.get("alt") or imagem.get("altText") or ""})
    return imagens


def _imagens(dados):
    # `media` com `nodes` e a consulta GraphQL; o webhook REST manda `images` (com a
    # MediaImage em admin_graphql_api_id) e uma lista `media` em outro formato.
    if isinstance(dados.get("media"), dict):
        return _da_consulta(dados["media"])
    imagens = dados.get("images") or []
    return imagens.get("nodes") or [] if isinstance(imagens, dict) else imagens


def sincronizar_imagens(produto, dados):
    imagens = _imagens(dados)
    midias = {str(m.pk): m for m in produto.midias.all()}
    # Vinculo de midia apagada no hub nao reconhece nada: a foto volta a ser baixada.
    lista = vinculos.do_produto(produto, midias.values())
    loja = _Loja(lista)
    for posicao, imagem in enumerate(imagens):
        externo_id = str(imagem.get("id") or imagem.get("admin_graphql_api_id") or "")
        origem_url = imagem.get("src") or imagem.get("url") or ""
        if not externo_id or not origem_url:
            continue
        alt = (imagem.get("alt") or imagem.get("altText") or "")[:255]
        vinculo = loja.reconhecer(externo_id, origem_url)
        if vinculo and (vinculo.metadata or {}).get("enviado_src"):
            _completar_eco(vinculo, externo_id, origem_url)
            lista.remove(vinculo)
            continue
        try:
            _importar(produto, imagem, vinculo, midias, externo_id, origem_url, alt, posicao)
        except ImagemShopifyErro as erro:
            # Uma foto ruim nao derruba o produto nem as outras fotos; sem vinculo, ela
            # e tentada de novo na proxima sincronizacao.
            avisar(str(erro), recurso="produtos", id=produto.pk, descricao=produto.nome,
                   id_externo=externo_id)


def _completar_eco(vinculo, externo_id, url):
    extras = {"imagem_id": externo_id} if externo_id != vinculo.external_id else {}
    vinculos.gravar_cdn(vinculo, url, **extras)


def _importar(produto, imagem, vinculo, midias, externo_id, url, alt, posicao):
    """Foto da loja: a mesma CDN reaproveita o arquivo local; CDN nova baixa de novo."""
    base = midias.get(vinculo.object_id) if vinculo else None
    anterior = (vinculo.metadata or {}).get("shopify_src") if vinculo else ""
    mesma_url = base and anterior and vinculos.sem_versao(anterior) == vinculos.sem_versao(url)
    # As copias (uma linha por variante) dividem o arquivo local da midia do vinculo.
    copias = [m for m in midias.values() if base and m.url == base.url]
    url_local = base.url if mesma_url else _baixar(url)
    ids_variantes = imagem.get("variantIds") or imagem.get("variant_ids") or []
    for variante in _variantes(produto, ids_variantes):
        midia = next((m for m in copias if m.variante_id == variante.pk), None)
        midia = midia or MidiaProduto(produto=produto, variante=variante, origin=Origin.SHOPIFY)
        midia.url, midia.alt_text, midia.posicao = url_local, alt, posicao
        midia.save()
        base = base or midia
    if vinculo is not None:
        # O mesmo vinculo passa a apontar o id/CDN atuais: criar outro deixaria dois
        # vinculos para a mesma midia.
        vinculo.external_id, vinculo.metadata = externo_id, {"shopify_src": url}
        vinculo.save(update_fields=["external_id", "metadata", "updated_at"])
    elif base is not None:
        vinculos.vincular(base, externo_id, {"shopify_src": url})
