"""Dados do produto do Shopify no Produto do hub: SEO, descricao, tags, colecoes, status.

Mapeamento (Product da Admin GraphQL 2026-07 -> Produto):
- title: so na criacao (recursos.produto); depois o nome e do hub e o webhook nao
  o troca (regra antiga, tests/test_webhooks.py), salvo na sincronizacao de importacao
  (`sobrescrever`); handle -> slug (se estiver livre);
- descriptionHtml -> descricao; vendor -> fornecedor;
- seo.title/seo.description -> seo_titulo/seo_descricao (so quando a loja tem valor);
- status ACTIVE/DRAFT/ARCHIVED -> publish/draft/archived; publishedAt -> publicado_em;
- tags -> Tag (criada pelo nome); collections -> categorias ja vinculadas;
- productType -> metadata do vinculo "produtos": o hub nao tem campo para ele (o
  `tipo` do Produto e o tipo do WooCommerce: simples, variavel...).
Com `sobrescrever`, valor vazio da loja tambem apaga (SEO) e as categorias do hub
saem se a colecao nao esta na loja. Campo ausente na carga (webhook REST de
reserva) nao mexe no que o hub tem.
"""

from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from apps.core.models import ExternalReference, Origin
from apps.loja.models import Produto, Tag
from apps.shopify.envio.produtos import STATUS as STATUS_ENVIO

STATUS = {
    "ACTIVE": Produto.Status.PUBLICADO,
    "DRAFT": Produto.Status.RASCUNHO,
    "ARCHIVED": Produto.Status.ARQUIVADO,
}


def _status(produto, status_loja):
    status_loja = str(status_loja or "").upper()
    if status_loja not in STATUS:
        return produto.status
    # Lixeira, pendente e privado nao existem na loja: se o hub ja corresponde ao
    # status de la (lixeira -> ARCHIVED), o detalhe do hub fica.
    if STATUS_ENVIO.get(produto.status, "DRAFT") == status_loja:
        return produto.status
    return STATUS[status_loja]


def _slug(produto, handle):
    slug = slugify(handle or "", allow_unicode=True)
    if not slug or slug == produto.slug:
        return produto.slug
    ocupado = Produto.objects.filter(slug=slug).exclude(pk=produto.pk).exists()
    return produto.slug if ocupado else slug


def _campos(produto, dados, sobrescrever=False):
    if sobrescrever and dados.get("title"):
        produto.nome = dados["title"][:255]
    produto.slug = _slug(produto, dados.get("handle"))
    if "descriptionHtml" in dados:
        produto.descricao = dados.get("descriptionHtml") or ""
    if "vendor" in dados:
        produto.fornecedor = (dados.get("vendor") or "")[:150]
    seo = dados.get("seo") or {}
    # SEO vazio na loja quer dizer "usa o titulo do produto": nao apaga o do hub.
    if seo.get("title") or sobrescrever:
        produto.seo_titulo = (seo.get("title") or "")[:255]
    if seo.get("description") or sobrescrever:
        produto.seo_descricao = seo.get("description") or ""
    if "publishedAt" in dados:
        produto.publicado_em = parse_datetime(dados["publishedAt"] or "")
    produto.status = _status(produto, dados.get("status"))


def _tags(dados):
    nomes = dados["tags"]
    if isinstance(nomes, str):  # webhook REST: "sala, azul"
        nomes = nomes.split(",")
    tags = []
    for nome in filter(None, (str(n).strip()[:100] for n in nomes)):
        tag, _ = Tag.objects.get_or_create(
            nome_normalizado=nome.casefold(),
            defaults={"nome": nome, "slug": slugify(nome), "origin": Origin.SHOPIFY})
        tags.append(tag)
    return tags


def _categorias(produto, colecoes, sobrescrever=False):
    """Categorias das colecoes ja importadas; as do hub sem colecao ficam.

    Na importacao (`sobrescrever`) o que nao esta nas colecoes da loja sai, desde
    que a lista veio inteira.
    """
    ligadas = dict(ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type="categorias",
    ).values_list("object_id", "external_id"))
    ids_loja = {(c or {}).get("id") for c in colecoes.get("nodes") or []}
    da_loja = [int(pk) for pk, gid in ligadas.items() if gid in ids_loja]
    cortada = (colecoes.get("pageInfo") or {}).get("hasNextPage")
    atuais = set(produto.categorias.values_list("pk", flat=True))
    # Lista cortada nao prova que o produto saiu de uma colecao: so acrescenta.
    fica = atuais if cortada else (
        set() if sobrescrever else {pk for pk in atuais if str(pk) not in ligadas})
    return fica | set(da_loja)


def _vinculo(produto, dados):
    vinculo = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type="produtos", external_id=dados["id"],
    ).first()
    if vinculo is None or "productType" not in dados:
        return
    meta = {**(vinculo.metadata or {}), "product_type": dados.get("productType") or ""}
    if meta != vinculo.metadata:
        vinculo.metadata = meta
        vinculo.save(update_fields=["metadata", "updated_at"])


def aplicar(produto, dados, sobrescrever=False):
    _campos(produto, dados, sobrescrever)
    produto.save()
    if "tags" in dados:
        produto.tags.set(_tags(dados))
    if isinstance(dados.get("collections"), dict):
        produto.categorias.set(_categorias(produto, dados["collections"], sobrescrever))
    _vinculo(produto, dados)
    return produto
