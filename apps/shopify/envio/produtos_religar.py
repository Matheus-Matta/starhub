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
"""

from apps.core.models import ExternalReference
from apps.shopify.cliente import ShopifyErro

PELO_SKU = """query($q: String!) {
  productVariants(first: 10, query: $q) { nodes { product { id } } }
}"""
SUMIU = "Product does not exist"


def sumiu(erro):
    return SUMIU in str(erro)


def _referencias(enviador, entidade):
    return ExternalReference.all_objects.filter(
        account_id=enviador.configuracao.account_id, platform=enviador.plataforma,
        entity_type=entidade)


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
    """Tira o vinculo do produto velho e os de variantes/fotos que apontavam para ele."""
    # Todos os do produto (um produto do hub = um da loja), qualquer que seja o formato
    # do id guardado: sobrar um velho faria o proximo envio cair nele de novo.
    _referencias(enviador, enviador._entidade()).filter(object_id=str(produto.pk)).delete()
    variantes = [str(pk) for pk in produto.variantes.values_list("pk", flat=True)]
    _referencias(enviador, "variantes").filter(object_id__in=variantes).delete()
    midias = [str(pk) for pk in produto.midias.values_list("pk", flat=True)]
    _referencias(enviador, "midias").filter(object_id__in=midias).delete()


def religar(enviador, produto, velho):
    """gid do produto da loja achado pelo SKU (ja vinculado), ou None."""
    novo = _da_loja_pelo_sku(enviador, produto)
    if novo is None:
        return None
    dono = _referencias(enviador, enviador._entidade()).filter(external_id=novo).exclude(
        object_id=str(produto.pk)).first()
    if dono is not None:
        raise ShopifyErro(
            f"O produto {velho} nao existe mais na loja e o SKU dele esta no produto {novo}, "
            f"que ja e de outro produto do hub (#{dono.object_id}): SKU repetido. "
            "Corrija o SKU em um dos dois e sincronize de novo.")
    esquecer(enviador, produto, velho)
    enviador.vincular(produto, novo)
    return novo


def atualizar(enviador, produto, produto_gid):
    """`enviador._atualizar`, refeito pelo SKU (ou criando) se o id sumiu da loja."""
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
