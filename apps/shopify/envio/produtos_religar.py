"""Produto ligado a um id que nao existe mais no Shopify: acha pelo SKU, ou cria de novo.

Produto apagado e recriado na loja (ou importado de novo) deixava o vinculo do hub no
id velho: o update falhava com "id: Product does not exist" mesmo com o SKU na loja
(tarefa #100056, SOFA TORONTO). Agora, nessa resposta:

1. o SKU de alguma variante do hub acha o produto na loja (productVariants) -> o
   vinculo passa a ele e o update segue (menos se esse produto da loja ja e de OUTRO
   produto do hub: SKU repetido, nao se rouba o vinculo);
2. nenhum produto com o SKU -> o vinculo velho sai e, com Enviar > Produtos > Criar
   ligado, o produto e criado de novo; desligado, o erro explica o que fazer.

Vinculos de variantes e de fotos do produto velho saem junto: apontavam para la.

Id que EXISTE mas e de outro produto (vinculo trocado) nao da erro nenhum: antes de
alterar, `conferir` le os SKUs do produto do id. Nenhum bate com o hub -> busca pelo
SKU e altera o produto achado. A busca nao acha nada -> segue pelo id: e o SKU trocado
no hub (2822 -> 2822A), que so chega a loja por este update.
"""

import logging

from apps.core.models import ExternalReference
from apps.shopify.cliente import ShopifyErro
from apps.shopify.contexto import avisar
from apps.shopify.envio import produtos_midias_religar as midias_religar

logger = logging.getLogger(__name__)

PELO_SKU = """query($q: String!) {
  productVariants(first: 10, query: $q) { nodes { product { id } } }
}"""
CONFERIR = """query($id: ID!) {
  product(id: $id) { id variants(first: 250) { nodes { sku } } }
}"""
SUMIU = "Product does not exist"


def sumiu(erro):
    return SUMIU in str(erro)


def _referencias(enviador, entidade):
    return ExternalReference.all_objects.filter(
        account_id=enviador.configuracao.account_id, platform=enviador.plataforma,
        entity_type=entidade)


def _skus(itens):
    return {(s or "").strip() for s in itens} - {""}


def _da_loja_pelo_sku(enviador, produto):
    achados = set()
    for sku in produto.variantes.exclude(sku="").values_list("sku", flat=True):
        sku = sku.strip().replace('"', "")
        if not sku:
            continue
        dados = enviador.cliente.graphql(PELO_SKU, {"q": f'sku:"{sku}"'}) or {}
        nodes = (dados.get("productVariants") or {}).get("nodes") or []
        achados.update((n.get("product") or {}).get("id") for n in nodes)
    achados.discard(None)
    return achados.pop() if len(achados) == 1 else None


def esquecer(enviador, produto, _velho=None):
    """Tira o vinculo do produto velho e os de variantes/fotos que apontavam para ele.
    Devolve {pk da midia: metadata} das fotos: a referencia para casar no produto novo."""
    # Todos os do produto (um produto do hub = um da loja), qualquer que seja o formato
    # do id guardado: sobrar um velho faria o proximo envio cair nele de novo.
    _referencias(enviador, enviador._entidade()).filter(object_id=str(produto.pk)).delete()
    variantes = [str(pk) for pk in produto.variantes.values_list("pk", flat=True)]
    _referencias(enviador, "variantes").filter(object_id__in=variantes).delete()
    midias = _referencias(enviador, "midias").filter(
        object_id__in=[str(pk) for pk in produto.midias.values_list("pk", flat=True)])
    antigos = dict(midias.values_list("object_id", "metadata"))
    midias.delete()
    return antigos


def _tomar(enviador, produto, novo):
    """Passa o produto (e as fotos, casadas pela referencia) para o `novo` da loja."""
    antigos = esquecer(enviador, produto)
    enviador.vincular(produto, novo)
    midias_religar.refazer(enviador, produto, novo, antigos)


def _dono(enviador, produto, gid):
    """Outro produto do hub ja ligado a esse produto da loja (SKU repetido), ou None."""
    return _referencias(enviador, enviador._entidade()).filter(external_id=gid).exclude(
        object_id=str(produto.pk)).first()


def conferir(enviador, produto, produto_gid):
    """gid que o update deve usar: o do vinculo, ou o achado pelo SKU se o do vinculo e
    de outro produto da loja (nenhum SKU em comum)."""
    loja = (enviador.cliente.graphql(CONFERIR, {"id": produto_gid}) or {}).get("product")
    if loja is None:
        return produto_gid  # sumiu: o productUpdate responde SUMIU e `atualizar` religa
    da_loja = _skus(n.get("sku") for n in (loja.get("variants") or {}).get("nodes") or [])
    do_hub = _skus(produto.variantes.values_list("sku", flat=True))
    if not da_loja or not do_hub or da_loja & do_hub:
        return produto_gid
    novo = _da_loja_pelo_sku(enviador, produto)
    if novo is None or novo == produto_gid:
        return produto_gid
    dono = _dono(enviador, produto, novo)
    if dono is not None:
        texto = (f"O produto {produto_gid} da loja nao tem nenhum SKU do produto #{produto.pk}"
                 f", e o SKU esta no {novo}, que ja e do produto #{dono.object_id} do hub: "
                 "SKU repetido. Seguiu pelo id guardado; corrija o SKU em um dos dois.")
        logger.warning(texto)
        avisar(texto, recurso="produtos", id=str(produto.pk))
        return produto_gid
    logger.info("Produto %s: vinculo %s trocado por %s (achado pelo SKU)",
                produto.pk, produto_gid, novo)
    _tomar(enviador, produto, novo)
    return novo


def religar(enviador, produto, velho):
    """gid do produto da loja achado pelo SKU (ja vinculado), ou None."""
    novo = _da_loja_pelo_sku(enviador, produto)
    if novo is None:
        return None
    dono = _dono(enviador, produto, novo)
    if dono is not None:
        raise ShopifyErro(
            f"O produto {velho} nao existe mais na loja e o SKU dele esta no produto {novo}, "
            f"que ja e de outro produto do hub (#{dono.object_id}): SKU repetido. "
            "Corrija o SKU em um dos dois e sincronize de novo.")
    _tomar(enviador, produto, novo)
    return novo


def atualizar(enviador, produto, produto_gid):
    """`enviador._atualizar` no produto certo: conferido pelo SKU antes, e refeito pelo
    SKU (ou criando) se o id sumiu da loja."""
    produto_gid = conferir(enviador, produto, produto_gid)
    try:
        return enviador._atualizar(produto, produto_gid)
    except ShopifyErro as erro:
        if not sumiu(erro):
            raise
        novo = religar(enviador, produto, produto_gid)
        if novo:
            return enviador._atualizar(produto, novo)
        if not enviador.configuracao.habilitado("enviar", "produtos", "create"):
            raise ShopifyErro(
                f"{erro} e nenhum produto da loja tem o SKU dele. Ligue Enviar > Produtos > "
                "Criar para o hub criar de novo, ou importe o produto da loja.") from erro
        esquecer(enviador, produto, produto_gid)
        enviador.vincular(produto, enviador.criar(produto))
        return None
