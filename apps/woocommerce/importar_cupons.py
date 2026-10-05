"""Cupom da loja WooCommerce no hub.

    cupom, criado = importar_cupom({"id": 3, "code": "promo10", "discount_type": "percent",
                                    "amount": "10.00", "minimum_amount": "100.00"})

No Woo o cupom e o codigo que o cliente digita; no hub ele vira o nome (o `code` do
hub e chave interna). Sem vinculo, o mesmo nome e o mesmo cupom. O que so o Woo
conhece (limite por e-mail, valor maximo) fica no metadata do vinculo.
"""

from datetime import UTC

from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.core.models import Origin
from apps.loja.models import Categoria, Cupom, Produto
from apps.woocommerce import vinculos
from apps.woocommerce.importar_catalogo import preco

ORIGEM = Origin.WOOCOMMERCE
TIPOS = {"percent": Cupom.TipoDesconto.PERCENTUAL, "fixed_cart": Cupom.TipoDesconto.VALOR_FIXO,
         "fixed_product": Cupom.TipoDesconto.VALOR_FIXO}


def _data(bruto):
    momento = parse_datetime(bruto) if bruto else None
    return momento.replace(tzinfo=UTC) if momento and momento.tzinfo is None else momento


def _tipo_e_valor(dados):
    valor = preco(dados.get("amount"))
    if dados.get("free_shipping") and not valor:
        return Cupom.TipoDesconto.FRETE_GRATIS, valor or 0
    return TIPOS.get(dados.get("discount_type"), Cupom.TipoDesconto.VALOR_FIXO), valor or 0


def _do_hub(modelo, recurso, ids):
    return [obj for obj in (vinculos.existente(recurso, modelo, i) for i in ids or []) if obj]


def _campos(cupom, dados):
    cupom.discount_type, cupom.value = _tipo_e_valor(dados)
    cupom.free_shipping = bool(dados.get("free_shipping"))
    cupom.description = dados.get("description") or ""
    cupom.status = (Cupom.Status.ATIVO if dados.get("status", "publish") == "publish"
                    else Cupom.Status.RASCUNHO)
    cupom.ends_at = _data(dados.get("date_expires_gmt"))
    cupom.usage_limit = dados.get("usage_limit") or None
    cupom.usage_limit_per_customer = dados.get("usage_limit_per_user") or None
    cupom.usage_count = int(dados.get("usage_count") or 0)
    cupom.stacking_policy = (Cupom.Combinacao.NAO_COMBINA if dados.get("individual_use")
                             else Cupom.Combinacao.COMBINA)
    cupom.excluir_promocao = bool(dados.get("exclude_sale_items"))
    minimo = preco(dados.get("minimum_amount"))
    cupom.minimum_requirement = (Cupom.RequisitoMinimo.SUBTOTAL if minimo
                                 else Cupom.RequisitoMinimo.NENHUM)
    cupom.minimum_subtotal = minimo


def _listas(cupom, dados):
    produtos = _do_hub(Produto, "produtos", dados.get("product_ids"))
    categorias = _do_hub(Categoria, "categorias", dados.get("product_categories"))
    cupom.produtos.set(produtos)
    cupom.categorias.set(categorias)
    cupom.produtos_excluidos.set(_do_hub(Produto, "produtos", dados.get("excluded_product_ids")))
    cupom.categorias_excluidas.set(
        _do_hub(Categoria, "categorias", dados.get("excluded_product_categories")))
    E = Cupom.ElegibilidadeProduto
    cupom.product_eligibility = E.PRODUTOS if produtos else E.CATEGORIAS if categorias else E.TODOS
    cupom.save(update_fields=["product_eligibility", "updated_at"])


@transaction.atomic
def importar_cupom(dados):
    codigo = str(dados.get("code") or "").strip()[:150]
    if not codigo:
        return None, False
    cupom = vinculos.existente("cupons", Cupom, dados.get("id"))
    cupom = cupom or Cupom.objects.filter(name__iexact=codigo).order_by("pk").first()
    criado = cupom is None
    cupom = cupom or Cupom(name=codigo, origin=ORIGEM)
    _campos(cupom, dados)
    cupom.save()
    _listas(cupom, dados)
    vinculos.referenciar("cupons", dados.get("id"), cupom, metadata={
        "codigo": codigo, "discount_type": dados.get("discount_type") or "",
        "maximum_amount": dados.get("maximum_amount") or "",
        "email_restrictions": dados.get("email_restrictions") or []})
    return cupom, criado
