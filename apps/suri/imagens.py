"""Fotos do produto do Suri no hub: pela referencia (webhook) ou do zero (Sincronizar)."""

from urllib.parse import urlsplit

from apps.core.imagens_iguais import mesmo_arquivo
from apps.core.imagens_remotas import ImagemErro, baixar
from apps.core.models import Origin
from apps.loja.models import MidiaProduto
from apps.loja.services.midias import sincronizar_midias, url_da_foto
from apps.loja.services.midias_refazer import refazer as refazer_galeria
from apps.suri import vinculos
from apps.suri.contexto import avisar
from apps.suri.envio.produtos_corpo import FOTO_PADRAO


def _url(imagem):
    return ((imagem or {}).get("url") or "").strip()


def _nao_importada(produto, dados, erro, consequencia=""):
    avisar(f"Imagem nao importada: {erro}{consequencia}", recurso="produtos", id=produto.pk,
           descricao=produto.nome, id_externo=dados.get("id"))


def importar(produto, dados):
    """Foto ja baixada (vinculo "midias" pela URL do Suri) nao baixa de novo."""
    lista = []
    for imagem in dados.get("images") or []:
        url = _url(imagem)
        if not url:
            continue
        midia = vinculos.existente("midias", MidiaProduto, url)
        if midia is not None:
            lista.append({"id": midia.pk, "src": midia.url, "alt": midia.alt_text, "_url": url})
            continue
        try:
            lista.append({"id": None, "src": url_da_foto(produto, baixar(url), lista),
                          "alt": imagem.get("description") or "", "_url": url})
        except ImagemErro as erro:
            _nao_importada(produto, dados, erro)
    padrao = produto.variantes.filter(is_default=True).first() or produto.variantes.first()
    if not padrao or not lista:
        return
    sincronizar_midias(padrao, [{k: v for k, v in i.items() if k != "_url"} for i in lista])
    # Pela url, e nao pela ordem: foto repetida na loja e uma linha so no hub.
    por_url = {mesmo_arquivo(m.url): m for m in padrao.midias.all()}
    for item in lista:
        if midia := por_url.get(mesmo_arquivo(item["src"])):
            vinculos.referenciar("midias", item["_url"], midia)


def _da_loja(produto, dados):
    """{url: (texto, [variantes])}, na ordem; foto sem variacao vai para a padrao. A foto
    padrao que o hub manda no lugar da vazia nao e foto do produto."""
    padrao = produto.variantes.filter(is_default=True).first() or produto.variantes.first()
    fotos = {}
    for imagem in dados.get("images") or []:
        fotos.setdefault(_url(imagem), (imagem.get("description") or "", []))
    for dimensao in dados.get("dimensions") or []:
        imagem = dimensao.get("image")
        variante = vinculos.existente("variantes", produto.variantes.model, vinculos.id_variacao(
            str(dados["id"]), dimensao.get("sku")))
        if variante is not None and variante.produto_id == produto.pk:
            fotos.setdefault(_url(imagem), ((imagem or {}).get("description") or "", []))[
                1].append(variante)
    return {url: (texto, variantes or [padrao]) for url, (texto, variantes) in fotos.items()
            if url and not urlsplit(url).path.endswith(FOTO_PADRAO)}


def refazer(produto, dados):
    """Sincronizar > Importar: saem as fotos do hub, entram as do Suri."""
    fotos = []
    try:
        for posicao, (url, (texto, variantes)) in enumerate(_da_loja(produto, dados).items()):
            src = baixar(url)
            fotos += [{"variante": v, "src": src, "alt": texto, "posicao": posicao,
                       "externo": url, "metadata": {}} for v in variantes]
    except ImagemErro as erro:
        _nao_importada(produto, dados, erro, " As fotos do hub foram mantidas.")
        return
    refazer_galeria(produto, fotos, Origin.SURI)
