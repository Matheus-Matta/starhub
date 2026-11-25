"""Sincronizar > Importar: as fotos do hub saem e entram as do Shopify, por variacao.

Foto usada por uma variacao na loja vai para ela; sem variacao, para a padrao. Nada muda no
hub se a loja nao tem foto, se alguma nao baixou ou se ainda ha foto em processamento la.
"""

from apps.core.models import Origin
from apps.loja.services.midias_refazer import refazer as refazer_galeria
from apps.shopify import midias as vinculos
from apps.shopify.contexto import avisar
from apps.shopify.imagens import imagens_da_loja, sincronizar_imagens
from apps.shopify.imagens_baixar import ImagemShopifyErro, _baixar
from apps.shopify.imagens_gravar import variantes_por_gid

EM_PROCESSAMENTO = ("PROCESSING", "UPLOADED")
# A consulta do produto corta em 100 fotos; 250 e o maximo da loja. Custo: 504.
FOTOS = """query($id: ID!) { product(id: $id) { media(first: 250) {
  nodes { id alt ... on MediaImage { status image { url altText } } } } } }"""
# A parte: com as fotos passaria dos 1000 pontos. Custo: 1 + 2 + 200 x 4 = 803.
DAS_VARIANTES = """query($id: ID!) { product(id: $id) { variants(first: 200) {
  nodes { id media(first: 1) { nodes { id } } } } } }"""


def _das_variantes(cliente, produto, produto_gid):
    """{gid da foto: [variantes do hub]}."""
    if produto.variantes.count() < 2:
        return {}
    loja = (cliente.graphql(DAS_VARIANTES, {"id": produto_gid}) or {}).get("product") or {}
    saida = {}
    for no in (loja.get("variants") or {}).get("nodes") or []:
        for foto in (no.get("media") or {}).get("nodes") or []:
            saida.setdefault(foto["id"], []).append(no["id"])
    return {foto: variantes_por_gid(produto, gids) for foto, gids in saida.items()}


def _completa(cliente, dados):
    if (dados["media"].get("pageInfo") or {}).get("hasNextPage"):
        loja = (cliente.graphql(FOTOS, {"id": dados["id"]}) or {}).get("product") or {}
        return {**dados, "media": loja.get("media") or {}}
    return dados


def _baixadas(produto, dados, das_variantes):
    fotos = []
    for posicao, imagem in enumerate(imagens_da_loja(dados)):
        src, alt = _baixar(imagem["src"]), (imagem["alt"] or "")[:255]
        for variante in das_variantes.get(imagem["id"]) or [produto.variante_padrao]:
            fotos.append({"variante": variante, "src": src, "alt": alt, "posicao": posicao,
                          "externo": imagem["id"], "metadata": {
                              "shopify_src": imagem["src"],
                              "visto": {"alt_text": alt, "posicao": posicao}}})
    return fotos


def _manter(produto, dados, motivo):
    avisar(f"Fotos do hub mantidas: {motivo}", recurso="produtos", id=produto.pk,
           descricao=produto.nome, id_externo=dados.get("id") or "")


def refazer(produto, dados):
    cliente = vinculos.cliente_da_loja()
    if cliente is None or not isinstance(dados.get("media"), dict):
        return sincronizar_imagens(produto, dados)  # corpo do webhook: sem a lista completa
    dados = _completa(cliente, dados)
    if any((n or {}).get("status") in EM_PROCESSAMENTO
           for n in dados["media"].get("nodes") or []):
        return _manter(produto, dados, "ainda ha foto em processamento no Shopify. "
                       "Sincronize de novo em alguns minutos.")
    if not imagens_da_loja(dados):
        if produto.midias.exists():
            _manter(produto, dados, "o produto nao tem foto no Shopify.")
        return None
    produto.__dict__.pop("_variante_padrao_cache", None)
    try:
        fotos = _baixadas(produto, dados, _das_variantes(cliente, produto, dados["id"]))
    except ImagemShopifyErro as erro:
        return _manter(produto, dados, f"{erro} Corrija a foto na loja e sincronize de novo.")
    return refazer_galeria(produto, fotos, Origin.SHOPIFY)
