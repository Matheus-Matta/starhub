"""Qual produto e qual variante do hub sao os da loja Shopify: SKU primeiro, depois o id.

Produto cadastrado no hub (ou pelo ERP) com o mesmo SKU nao tinha vinculo com o
Shopify: o update ficava "Registro nao encontrado" ou, com Receber > Criar, duplicava
o produto. A ordem agora:

1. SKU de alguma variante recebida -> o produto dessa variante (o vinculo passa a ele),
   menos quando esse produto ja e de OUTRO produto da loja (SKU repetido na loja);
2. o vinculo do id do Shopify (ExternalReference);
3. nenhum dos dois: quem chamou cria.

Dentro do produto a variante segue a mesma ordem: SKU, vinculo, e a padrao quando a
loja so tem uma.

    obj = localizar_produto(dados)                      # Produto ou None
    variante = variante_do_produto(obj, recebida, 2)    # VarianteProduto ou None
"""

from apps.core.models import ExternalReference, Origin
from apps.loja.models import VarianteProduto


def _sku(item):
    return (item.get("sku") or "").strip()


def _recebidas(dados):
    return (dados.get("variants") or {}).get("nodes") or []


def _pelo_sku(dados):
    for recebida in _recebidas(dados):
        sku = _sku(recebida)
        variante = (VarianteProduto.objects.filter(sku=sku).select_related("produto").first()
                    if sku else None)
        if variante is not None:
            return variante.produto
    return None


def localizar_produto(dados):
    from apps.shopify.recursos import _existente

    obj = _pelo_sku(dados)
    if obj is not None and ExternalReference.objects.filter(
            platform=Origin.SHOPIFY, entity_type="produtos", object_id=str(obj.pk)).exclude(
            external_id=dados["id"]).exists():
        obj = None  # ja e de outro produto da loja: SKU repetido na loja, vale o id
    if obj is None:
        return _existente("produtos", dados["id"])
    # SKU vale mais que um vinculo antigo: o proximo webhook ja acha pelo id tambem.
    ExternalReference.objects.update_or_create(
        platform=Origin.SHOPIFY, entity_type="produtos", external_id=dados["id"],
        defaults={"object_id": str(obj.pk), "origin": Origin.SHOPIFY})
    return obj


def _por_referencia(produto, externo_id):
    referencia = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type="variantes", external_id=externo_id).first()
    return produto.variantes.filter(pk=referencia.object_id).first() if referencia else None


def variante_do_produto(produto, recebida, total):
    sku = _sku(recebida)
    variante = produto.variantes.filter(sku=sku).first() if sku else None
    variante = variante or _por_referencia(produto, recebida.get("id"))
    if variante is None and total == 1:
        variante = produto.variante_padrao
    return variante
