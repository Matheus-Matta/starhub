"""Vinculo de cada midia do produto com a midia do Shopify (ExternalReference "midias").

Os dados do Shopify ficam no vinculo, nunca no metadados da MidiaProduto: cada
marketplace tem o seu vinculo, e o registro do hub nao mistura dado de loja.

metadata do vinculo:
- "enviado_src": URL do hub mandada ao Shopify (a foto nasceu no hub);
- "shopify_src": URL da CDN do Shopify vista na ultima importacao;
- "imagem_id": id que a importacao viu para a mesma foto, quando nao e o do vinculo.

O id do vinculo e o da MediaImage. O webhook traz o mesmo id em
`images[].admin_graphql_api_id` (doc REST product-image 2026-07: `"id": 1001473911`
com `"admin_graphql_api_id": "gid://shopify/MediaImage/1072273211"`): o numero do
id REST e outro, entao ids so casam inteiros, nunca pelo numero.
"""

from urllib.parse import urljoin, urlsplit

from apps.core.models import ExternalReference, Origin
from apps.shopify.cliente import ShopifyClient
from apps.shopify.contexto import configuracao_atual

ENTIDADE = "midias"
PENDENTE = "pendente:"
# nodes(ids:): "Returns the list of nodes ... with the given IDs". A MediaImage so
# tem `image` pronta em READY ("Returns `null` until `status` is `READY`").
CONSULTA = """query($ids: [ID!]!) {
  nodes(ids: $ids) { id ... on MediaImage { status image { url } } }
}"""


def referencias(account_id):
    return ExternalReference.all_objects.filter(
        account_id=account_id, platform=Origin.SHOPIFY, entity_type=ENTIDADE
    )


def do_produto(produto, midias):
    """Vinculos das midias informadas, na ordem em que foram criados."""
    return list(referencias(produto.account_id).filter(
        object_id__in=[str(m.pk) for m in midias]
    ).order_by("created_at", "pk"))


def vincular(midia, external_id, metadata, produto_gid=""):
    # A chave e o id externo (indice unico referencia_externa_unica).
    referencia, _ = ExternalReference.all_objects.update_or_create(
        account_id=midia.account_id, platform=Origin.SHOPIFY, entity_type=ENTIDADE,
        external_id=str(external_id),
        defaults={"object_id": str(midia.pk), "metadata": metadata,
                  "external_parent_id": produto_gid, "origin": Origin.SHOPIFY},
    )
    return referencia


def sem_versao(url):
    """URL da CDN sem a query (?v=...): a mesma foto volta com outra versao na query."""
    partes = urlsplit(url or "")
    return f"{partes.netloc}{partes.path}"


def cliente_da_loja():
    """Cliente da loja da tarefa em andamento (webhook/sincronizacao), ou None."""
    configuracao = configuracao_atual()
    return ShopifyClient(configuracao) if configuracao is not None else None


def cdn_por_id(cliente, ids):
    """{id da MediaImage: URL da CDN} das midias ja prontas na loja (READY)."""
    ids = [i for i in ids if i and not i.startswith(PENDENTE)]
    if not ids or cliente is None:
        return {}
    dados = cliente.graphql(CONSULTA, {"ids": ids}) or {}
    return {
        node["id"]: node["image"]["url"]
        for node in dados.get("nodes") or []
        if node and node.get("status") == "READY" and (node.get("image") or {}).get("url")
    }


def sem_cdn(lista):
    """Vinculos de fotos enviadas pelo hub cuja URL da CDN ainda nao e conhecida."""
    return [v for v in lista if (v.metadata or {}).get("enviado_src")
            and not (v.metadata or {}).get("shopify_src")]


def gravar_cdn(vinculo, url, **extras):
    meta = {**(vinculo.metadata or {}), "shopify_src": url, **extras}
    if meta != vinculo.metadata:
        vinculo.metadata = meta
        vinculo.save(update_fields=["metadata", "updated_at"])


def url_publica(configuracao, url):
    """URL que o Shopify consegue baixar; "" quando o hub nao tem endereco publico.

    O MEDIA local devolve "/media/...": sem a URL publica do hub (a mesma dos
    webhooks) o Shopify falharia a midia em silencio.
    """
    url = (url or "").strip()
    if urlsplit(url).scheme in ("http", "https"):
        return url
    base = getattr(configuracao, "url_webhook", "") or ""
    if not url or not base:
        return ""
    return urljoin(base, url)
