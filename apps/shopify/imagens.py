"""Importa as imagens do produto do Shopify para o MEDIA do StarHub, sem duplicar.

Antes de baixar, a imagem e reconhecida pelo vinculo "midias" (apps/shopify/midias.py):
a) a URL da CDN e a mesma da ultima importacao (`shopify_src`), sem o `?v=`: a
   consulta GraphQL e o webhook devolvem o mesmo arquivo com versoes diferentes;
b) o id e o do vinculo (a MediaImage do envio) ou o `imagem_id` visto antes;
c) a URL de origem e a propria URL que o hub enviou (`enviado_src`);
d) nada bateu e ha foto enviada ainda sem CDN (estava em PROCESSING no envio):
   pergunta a loja a URL da CDN dessas midias pelo id do vinculo e compara.
e) foto do hub ainda sem vinculo com o mesmo nome de arquivo (o nome e um uuid): o eco
   chegou antes de o envio gravar o vinculo.
So baixa se nada bater, e se a loja confirmar que a foto esta la (webhook velho). Texto
alternativo nunca identifica: uma foto que falhou na loja faria o hub adotar outra foto
cadastrada la no lugar dela. Foto que nasceu no hub continua com a URL do hub: o eco so
completa o vinculo com a CDN. Foto apagada de um dos lados: midias_apagadas.py.
"""

from apps.shopify import imagens_gravar as gravar
from apps.shopify import midias as vinculos
from apps.shopify import midias_apagadas
from apps.shopify.contexto import avisar
from apps.shopify.imagens_baixar import ImagemShopifyErro


def _mesma(vinculo, externo_id, url):
    meta = vinculo.metadata or {}
    return (
        url == meta.get("enviado_src")
        or (meta.get("shopify_src")
            and vinculos.sem_versao(url) == vinculos.sem_versao(meta["shopify_src"]))
        or externo_id in (vinculo.external_id, meta.get("imagem_id"))
    )


def _eco(vinculo, url):
    """A foto que o hub mandou, intacta na loja; outro arquivo na CDN = trocada la."""
    meta = vinculo.metadata or {}
    cdn = meta.get("shopify_src")
    return bool(meta.get("enviado_src")) and (
        not cdn or url == meta["enviado_src"]
        or vinculos.sem_versao(cdn) == vinculos.sem_versao(url))


class _Loja:
    """Consulta a CDN das fotos enviadas ainda sem CDN, uma vez por importacao."""

    def __init__(self, lista, produto_gid):
        self.lista, self.cdn = lista, None
        self.produto_gid, self._agora = produto_gid, False
        self.cliente = vinculos.cliente_da_loja()

    def agora(self):
        """Fotos do produto na loja neste momento (None = nao da para saber). Perguntado
        depois de ler os vinculos: foto vinculada que falta aqui saiu mesmo."""
        if self._agora is False:
            self._agora = midias_apagadas.ids_na_loja(self.cliente, self.produto_gid)
        return self._agora

    def confirma(self, externo_id):
        return self.agora() is None or not externo_id.startswith(
            "gid://shopify/MediaImage/") or externo_id in self.agora()

    def reconhecer(self, externo_id, url):
        vinculo = next((v for v in self.lista if _mesma(v, externo_id, url)), None)
        if vinculo or not vinculos.sem_cdn(self.lista):
            return vinculo
        if self.cdn is None:
            # Erro da loja sobe: a execucao falha e e reprocessada, em vez de baixar
            # uma copia da foto que talvez seja a do proprio hub.
            ids = [v.external_id for v in vinculos.sem_cdn(self.lista)]
            self.cdn = vinculos.cdn_por_id(self.cliente, ids)
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


def imagens_da_loja(dados):
    # `media` com `nodes` e a consulta GraphQL; o webhook REST manda `images` (com a
    # MediaImage em admin_graphql_api_id) e uma lista `media` em outro formato.
    if isinstance(dados.get("media"), dict):
        return _da_consulta(dados["media"])
    imagens = dados.get("images") or []
    return imagens.get("nodes") or [] if isinstance(imagens, dict) else imagens


def _pelo_nome(lista, midias, externo_id, url):
    ligadas = {v.object_id for v in lista if not v.external_id.startswith(vinculos.PENDENTE)}
    for pk, midia in midias.items():
        if pk not in ligadas and vinculos.tem_nome_unico(midia.url) \
                and vinculos.e_o_arquivo(midia.url, url):
            vinculo = vinculos.vincular(midia, externo_id, {"enviado_src": midia.url})
            lista.append(vinculo)
            return vinculo
    return None


def sincronizar_imagens(produto, dados):
    midias = {str(m.pk): m for m in produto.midias.all()}
    lista = vinculos.do_produto(produto, midias.values())
    loja = _Loja(lista, str(dados.get("id") or ""))
    recebidas = {str(i.get("id") or i.get("admin_graphql_api_id") or ""): i
                 for i in imagens_da_loja(dados)}
    vistos = {v.pk: v for v in lista}
    apagadas = midias_apagadas.apagadas_no_hub(produto, list(recebidas))
    for posicao, (externo_id, imagem) in enumerate(recebidas.items()):
        url = imagem.get("src") or imagem.get("url") or ""
        if not externo_id or not url or externo_id in apagadas:
            continue
        alt = (imagem.get("alt") or imagem.get("altText") or "")[:255]
        vinculo = loja.reconhecer(externo_id, url) or _pelo_nome(lista, midias, externo_id, url)
        if vinculo is not None:
            vistos.pop(vinculo.pk, None)
        if vinculo and _eco(vinculo, url):
            _completar_eco(vinculo, externo_id, url)
            lista.remove(vinculo)
            continue
        try:
            if vinculo is not None and vinculo.object_id in midias:
                gravar.conhecida(produto, imagem, vinculo, midias, externo_id, url, alt, posicao)
            elif loja.confirma(externo_id):
                gravar.nova(produto, imagem, externo_id, url, alt, posicao)
        except ImagemShopifyErro as erro:
            # Uma foto ruim nao derruba o produto nem as outras fotos; sem vinculo, ela
            # e tentada de novo na proxima sincronizacao.
            avisar(str(erro), recurso="produtos", id=produto.pk, descricao=produto.nome,
                   id_externo=externo_id)
    faltam = midias_apagadas.candidatas(produto, loja.produto_gid, vistos.values(), recebidas)
    if faltam and loja.agora() is not None:
        midias_apagadas.tirar_do_hub(
            produto, [v for v in faltam if v.external_id not in loja.agora()])


def _completar_eco(vinculo, externo_id, url):
    extras = {"imagem_id": externo_id} if externo_id != vinculo.external_id else {}
    vinculos.gravar_cdn(vinculo, url, **extras)
