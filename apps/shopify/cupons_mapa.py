"""Desconto do Shopify (DiscountCodeNode da Admin GraphQL) -> campos do Cupom.

    campos, listas, extras = mapear(node)
    aplicar_listas(cupom, listas)   # depois que o cupom tem pk (ManyToMany)

O que o Cupom nao tem (segmentos, frete maximo, status SCHEDULED, gids que o
hub nao conhece) sai em `extras`, que vai para o vinculo (cupons_vinculo.py).
No sem `__typename` e o corpo magro do webhook sem consulta: so nome e status,
para nao zerar as regras.
"""

from decimal import Decimal

from django.utils.dateparse import parse_datetime

from apps.core.models import ExternalReference, Origin
from apps.loja.dinheiro import ZERO
from apps.loja.models import Categoria, Cliente, Cupom, Produto, VarianteProduto
from apps.shopify.pedidos_base import valor

Tipo, Regra = Cupom.TipoDesconto, Cupom.ElegibilidadeProduto
TAMANHO_NOME = Cupom._meta.get_field("name").max_length
# SCHEDULED e ativo com inicio no futuro: o starts_at ja segura ate a data.
_STATUS = {"ACTIVE": Cupom.Status.ATIVO, "SCHEDULED": Cupom.Status.ATIVO,
           "EXPIRED": Cupom.Status.EXPIRADO}


def _nodes(conexao):
    return (conexao or {}).get("nodes") or []


def _incompleta(*conexoes):
    return any(((c or {}).get("pageInfo") or {}).get("hasNextPage") for c in conexoes)


def codigos(node):
    desconto = node.get("codeDiscount") or {}
    return [str(c["code"]).strip() for c in _nodes(desconto.get("codes")) if c.get("code")]


def _valor(desconto):
    if desconto.get("__typename") == "DiscountCodeFreeShipping":
        return {"discount_type": Tipo.FRETE_GRATIS, "value": ZERO, "free_shipping": True}
    bruto = (desconto.get("customerGets") or {}).get("value") or {}
    if bruto.get("__typename") == "DiscountPercentage":
        # O Shopify manda a fracao (0.1 = 10%); o Cupom guarda o percentual.
        percentual = Decimal(str(bruto.get("percentage") or 0)) * 100
        return {"discount_type": Tipo.PERCENTUAL, "value": valor(str(percentual)),
                "free_shipping": False}
    if bruto.get("__typename") == "DiscountAmount":
        quantia = bruto.get("amount") or {}
        campos = {"discount_type": Tipo.VALOR_FIXO, "value": valor(quantia.get("amount")),
                  "free_shipping": False, "once_per_order": not bruto.get("appliesOnEachItem")}
        if quantia.get("currencyCode"):
            campos["currency"] = quantia["currencyCode"]
        return campos
    return {}  # Compre X leve Y e desconto de app: o Cupom nao tem esse tipo.


def _minimo(desconto):
    minimo = desconto.get("minimumRequirement") or {}
    if minimo.get("__typename") == "DiscountMinimumSubtotal":
        subtotal = (minimo.get("greaterThanOrEqualToSubtotal") or {}).get("amount")
        return {"minimum_requirement": Cupom.RequisitoMinimo.SUBTOTAL,
                "minimum_subtotal": valor(subtotal), "minimum_quantity": None}
    if minimo.get("__typename") == "DiscountMinimumQuantity":
        return {"minimum_requirement": Cupom.RequisitoMinimo.QUANTIDADE,
                "minimum_subtotal": None,
                "minimum_quantity": int(minimo.get("greaterThanOrEqualToQuantity") or 0) or None}
    return {"minimum_requirement": Cupom.RequisitoMinimo.NENHUM,
            "minimum_subtotal": None, "minimum_quantity": None}


def _clientes(desconto, listas, extras):
    contexto = desconto.get("context") or {}
    tipo = contexto.get("__typename")
    if tipo == "DiscountCustomers":
        listas["clientes"] = [c["id"] for c in contexto.get("customers") or []]
        return Cupom.ElegibilidadeCliente.CLIENTES
    if tipo == "DiscountCustomerSegments":
        extras["segmentos"] = [s.get("name") for s in contexto.get("segments") or []]
    elif tipo == "DiscountMarkets":
        extras["mercados"] = True
    return Cupom.ElegibilidadeCliente.TODOS


def _produtos(desconto, listas, extras):
    itens = (desconto.get("customerGets") or {}).get("items") or {}
    if itens.get("__typename") == "DiscountProducts":
        produtos, variantes = itens.get("products"), itens.get("productVariants")
        listas["produtos"] = [n["id"] for n in _nodes(produtos)]
        listas["variantes"] = [(n["id"], n.get("sku") or "") for n in _nodes(variantes)]
        extras["listas_incompletas"] = _incompleta(produtos, variantes)
        return Regra.VARIANTES if listas["variantes"] else Regra.PRODUTOS
    if itens.get("__typename") == "DiscountCollections":
        colecoes = itens.get("collections")
        listas["categorias"] = [n["id"] for n in _nodes(colecoes)]
        extras["listas_incompletas"] = _incompleta(colecoes)
        return Regra.CATEGORIAS
    return Regra.TODOS


def mapear(node):
    """(campos do Cupom, listas de gids ou None se o no nao traz as regras, extras)."""
    desconto = node.get("codeDiscount") or {}
    status = str(desconto.get("status") or "").upper()
    extras = {"id": node.get("id"), "tipo": desconto.get("__typename"), "status": status,
              "codigos": codigos(node)}
    campos = {"name": (desconto.get("title") or "").strip()[:TAMANHO_NOME]}
    if status in _STATUS:
        campos["status"] = _STATUS[status]
    if not desconto.get("__typename"):
        return campos, None, extras
    listas = {"produtos": [], "variantes": [], "categorias": [], "clientes": []}
    combina = desconto.get("combinesWith") or {}
    frete = desconto.get("maximumShippingPrice")
    if frete:
        extras["frete_maximo"] = str(valor(frete.get("amount")))
    extras["combina_com"] = combina
    campos.update({
        "description": desconto.get("summary") or "",
        "starts_at": parse_datetime(desconto["startsAt"]) if desconto.get("startsAt") else None,
        "ends_at": parse_datetime(desconto["endsAt"]) if desconto.get("endsAt") else None,
        "usage_limit": desconto.get("usageLimit"),
        "usage_limit_per_customer": 1 if desconto.get("appliesOncePerCustomer") else None,
        "usage_count": desconto.get("asyncUsageCount") or 0,
        "stacking_policy": (Cupom.Combinacao.COMBINA if any(combina.values())
                            else Cupom.Combinacao.NAO_COMBINA),
        **_valor(desconto), **_minimo(desconto),
        "customer_eligibility": _clientes(desconto, listas, extras),
        "product_eligibility": _produtos(desconto, listas, extras),
    })
    return campos, listas, extras


def _pelas_referencias(modelo, entidade, gids, faltando):
    ids = dict(ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type=entidade, external_id__in=gids,
    ).values_list("external_id", "object_id"))
    objetos = {str(o.pk): o for o in modelo.objects.filter(pk__in=ids.values())}
    achados = {gid: objetos[ids[gid]] for gid in gids if ids.get(gid) in objetos}
    faltando.extend(gid for gid in gids if gid not in achados)
    return achados


def aplicar_listas(cupom, listas):
    """Liga produtos, variantes, colecoes e clientes que o hub ja conhece e devolve
    os gids que ainda nao existem no hub."""
    faltando = []
    produtos = list(_pelas_referencias(Produto, "produtos", listas["produtos"], faltando)
                    .values())
    por_ref = _pelas_referencias(VarianteProduto, "variantes",
                                 [gid for gid, _sku in listas["variantes"]], [])
    variantes = []
    for gid, sku in listas["variantes"]:
        variante = por_ref.get(gid) or (
            VarianteProduto.objects.filter(sku=sku).first() if sku else None)
        if variante:
            variantes.append(variante)
        else:
            faltando.append(gid)
    if variantes:
        # Uma regra so no Cupom: produto inteiro + variante solta viram todas variantes.
        variantes += VarianteProduto.objects.filter(produto__in=produtos)
    cupom.produtos.set(produtos)
    cupom.variantes.set(variantes)
    cupom.categorias.set(_pelas_referencias(
        Categoria, "categorias", listas["categorias"], faltando).values())
    cupom.clientes.set(_pelas_referencias(
        Cliente, "clientes", listas["clientes"], faltando).values())
    return faltando
