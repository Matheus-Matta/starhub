"""Servico comprado pelo bloco do tema: linha propria no pedido, ligada ao produto.

O tema (Guia dos servicos) poe o produto e o servico no carrinho com a mesma
propriedade `_starhub_vinculo`. No pedido a linha do servico (variante do produto
escondido, servicos_envio.py) nao vira item: vira servico do item do produto, com
o valor somado nele, como no Suri. Sem a propriedade (servico posto a mao no
carrinho), vai para o primeiro item do pedido.
"""

from apps.core.models import ExternalReference, Origin
from apps.loja.dinheiro import ZERO, dinheiro
from apps.loja.models import Servico
from apps.shopify.contexto import configuracao_atual
from apps.shopify.pedidos_base import gid, soma_alocacoes, valor_com_fallback
from apps.shopify.servicos_envio import VARIANTES

PROPRIEDADE = "_starhub_vinculo"


def ligado():
    return bool(getattr(configuracao_atual(), "receber_servicos", False))


def servico_da_linha(linha):
    if not ligado():
        return None
    externo = gid("ProductVariant", linha.get("variant_id"))
    referencia = externo and ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type=VARIANTES, external_id=externo).first()
    if referencia:
        return Servico.objects.filter(pk=referencia.object_id).first()
    sku = str(linha.get("sku") or "").strip()
    return Servico.objects.filter(sku=sku).first() if sku else None


def vinculo(linha):
    return next((str(p.get("value") or "") for p in linha.get("properties") or []
                 if p.get("name") == PROPRIEDADE), "")


def somar(item, linha, servico):
    """Soma o servico no item e devolve o servico no formato de starhub.servicos."""
    quantidade = max(int(linha.get("quantity") or 1), 1)
    subtotal = dinheiro(valor_com_fallback(linha, "price", "price_set") * quantidade)
    desconto = soma_alocacoes(linha)
    total = dinheiro(max(subtotal - desconto, ZERO))
    item.subtotal += subtotal
    item.total += total
    item.total_desconto = item.subtotal - item.total
    item.save()
    return {"item_id": item.pk, "sku": item.sku, "servico": servico.nome,
            "servico_id": servico.pk, "opcao": "Sim", "preco": f"{total:.2f}"}
