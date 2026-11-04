"""Traduz as regras canonicas do cupom para os inputs de desconto da Shopify."""

from decimal import Decimal

from django.utils import timezone

from apps.core.models import ExternalReference, Origin
from apps.loja.models import Cupom, Produto
from apps.shopify.cliente import ShopifyErro


def _gids(objetos, entidade, rotulo):
    ids = [str(pk) for pk in objetos.values_list("pk", flat=True)]
    referencias = dict(ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type=entidade, object_id__in=ids,
    ).values_list("object_id", "external_id"))
    faltantes = [pk for pk in ids if pk not in referencias]
    if faltantes:
        raise ShopifyErro(
            f"Ha {len(faltantes)} {rotulo} sem vinculo com a Shopify. "
            "Sincronize produtos e clientes antes de enviar o cupom."
        )
    return [referencias[pk] for pk in ids]


def _contexto(cupom):
    regra = cupom.customer_eligibility
    if regra == Cupom.ElegibilidadeCliente.TODOS:
        return {"all": "ALL"}
    if regra == Cupom.ElegibilidadeCliente.CLIENTES:
        gids = _gids(cupom.clientes.all(), "clientes", "clientes")
        if not gids:
            raise ShopifyErro("Escolha ao menos um cliente para o cupom.")
        return {"customers": {"add": gids}}
    raise ShopifyErro(
        "A Shopify exige um segmento para cupom por tag de cliente. "
        "Use clientes especificos ou todos os clientes."
    )


def _itens(cupom):
    if (cupom.produtos_excluidos.exists() or cupom.categorias_excluidas.exists()
            or cupom.excluir_promocao):
        raise ShopifyErro(
            "A Shopify nao aceita as exclusoes deste cupom nativo. "
            "Remova produtos/categorias excluidos e a opcao de promocao."
        )
    regra = cupom.product_eligibility
    if regra == Cupom.ElegibilidadeProduto.TODOS:
        return {"all": True}
    if regra == Cupom.ElegibilidadeProduto.PRODUTOS:
        gids = _gids(cupom.produtos.all(), "produtos", "produtos")
        entrada = {"productsToAdd": gids}
    elif regra == Cupom.ElegibilidadeProduto.VARIANTES:
        gids = _gids(cupom.variantes.all(), "variantes", "variantes")
        entrada = {"productVariantsToAdd": gids}
    elif regra == Cupom.ElegibilidadeProduto.CATEGORIAS:
        gids = _gids(cupom.categorias.all(), "categorias", "categorias")
        return {"collections": {"add": gids}}
    else:
        produtos = Produto.objects.filter(tags__in=cupom.tags.all()).distinct()
        gids = _gids(produtos, "produtos", "produtos das tags")
        entrada = {"productsToAdd": gids}
    if not gids:
        raise ShopifyErro("A regra do cupom nao encontrou itens vinculados na Shopify.")
    return {"products": entrada}


def _minimo(cupom):
    if cupom.minimum_requirement == Cupom.RequisitoMinimo.SUBTOTAL:
        return {"subtotal": {
            "greaterThanOrEqualToSubtotal": f"{cupom.minimum_subtotal:.2f}"}}
    if cupom.minimum_requirement == Cupom.RequisitoMinimo.QUANTIDADE:
        return {"quantity": {"greaterThanOrEqualToQuantity": cupom.minimum_quantity}}
    return None


def _combinacao(cupom):
    permite = cupom.stacking_policy == Cupom.Combinacao.COMBINA
    return {"orderDiscounts": permite, "productDiscounts": permite,
            "shippingDiscounts": permite}


def _validar_regras_extras(cupom):
    regras = (
        (cupom.subtotal_maximo is not None, "subtotal maximo"),
        (cupom.quantidade_maxima is not None, "quantidade maxima"),
        (cupom.produtos_distintos_minimos is not None, "minimo de produtos distintos"),
        (cupom.produtos_distintos_maximos is not None, "maximo de produtos distintos"),
        (cupom.preco_item_minimo is not None, "preco minimo do item"),
        (cupom.preco_item_maximo is not None, "preco maximo do item"),
        (bool(cupom.dias_semana), "dias da semana"),
        (cupom.horario_inicio is not None, "horario inicial"),
        (cupom.horario_fim is not None, "horario final"),
        (cupom.minimum_requirement == Cupom.RequisitoMinimo.AMBOS,
         "subtotal e quantidade minimos juntos"),
    )
    ativas = [rotulo for ativa, rotulo in regras if ativa]
    if ativas:
        raise ShopifyErro(
            "O desconto nativo da Shopify nao suporta estas regras do cupom: "
            f"{', '.join(ativas)}. Remova-as ou use uma Shopify Function personalizada."
        )


def entrada(cupom, incluir_codigo=False):
    _validar_regras_extras(cupom)
    if cupom.first_order_only:
        raise ShopifyErro(
            "Cupom somente para a primeira compra exige um segmento na Shopify; "
            "desligue essa opcao antes de enviar."
        )
    if cupom.usage_limit_per_customer not in (None, 0, 1):
        raise ShopifyErro("A Shopify aceita somente um uso por cliente ou sem limite.")
    comum = {
        "title": cupom.name,
        "context": _contexto(cupom),
        "startsAt": (cupom.starts_at or timezone.now()).isoformat(),
        "endsAt": cupom.ends_at.isoformat() if cupom.ends_at else None,
        "usageLimit": cupom.usage_limit,
        "appliesOncePerCustomer": cupom.usage_limit_per_customer == 1,
        "minimumRequirement": _minimo(cupom),
        "combinesWith": _combinacao(cupom),
    }
    if incluir_codigo:
        comum["code"] = cupom.code.strip()
    if cupom.discount_type == Cupom.TipoDesconto.FRETE_GRATIS:
        if cupom.product_eligibility != Cupom.ElegibilidadeProduto.TODOS:
            raise ShopifyErro("Frete gratis da Shopify nao limita produtos elegiveis.")
        comum["destination"] = {"all": True}
        return comum
    if cupom.free_shipping:
        raise ShopifyErro(
            "A Shopify nao junta desconto de produto e frete gratis no mesmo codigo. "
            "Crie dois cupons ou desligue o frete gratis."
        )
    if cupom.discount_type == Cupom.TipoDesconto.PERCENTUAL:
        valor = {"percentage": float(Decimal(cupom.value) / Decimal("100"))}
    else:
        valor = {"discountAmount": {
            "amount": f"{cupom.value:.2f}", "appliesOnEachItem": not cupom.once_per_order}}
    comum["customerGets"] = {"value": valor, "items": _itens(cupom)}
    return comum
