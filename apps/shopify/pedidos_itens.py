"""Itens do pedido Shopify: um ItemPedido por line_item, ligado a variante do catalogo.

O id do line_item fica no vinculo ExternalReference "itens_pedido" (nunca nos
metadados do item, que saem no meta_data da API Woo): e por ele que o
orders/updated acha o item certo em vez de criar outro.
"""

from apps.core.models import ExternalReference, Origin
from apps.loja.dinheiro import ZERO, dinheiro, somar
from apps.loja.models import ItemPedido, Produto, VarianteProduto
from apps.loja.totais import valores_do_item
from apps.shopify.pedidos_base import gid, soma_alocacoes, valor, valor_com_fallback
from apps.shopify.pedidos_servicos import servicos_do_item

ENTIDADE = "itens_pedido"


def _variante(linha):
    """Referencia da variante -> SKU -> o produto e buscado no Shopify e importado."""
    externo = gid("ProductVariant", linha.get("variant_id"))
    referencia = externo and ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type="variantes", external_id=externo).first()
    variante = referencia and VarianteProduto.objects.filter(pk=referencia.object_id).first()
    sku = str(linha.get("sku") or "").strip()
    if not variante and sku:
        variante = VarianteProduto.objects.filter(sku=sku).first()
    if variante:
        return variante
    # Import tardio: o modulo chama a API do Shopify e o teste troca por um falso.
    # Erro sobe de proposito: o pedido inteiro volta e a execucao fica para reprocessar.
    from apps.shopify.pedidos_produtos import garantir_produto

    return garantir_produto(linha)


def _desconto(linha):
    """Desconto ja alocado pelo Shopify.

    total_discount (campo antigo) repete a soma das discount_allocations quando
    elas existem: somar os dois daria desconto em dobro.
    """
    alocado = soma_alocacoes(linha)
    return alocado if linha.get("discount_allocations") else valor(linha.get("total_discount"))


def _imposto(linha, taxas_inclusas):
    """Imposto ja embutido no preco nao soma de novo no total."""
    if taxas_inclusas:
        return ZERO
    return somar(taxa.get("price") for taxa in linha.get("tax_lines") or [])


def _gravar(item, linha, taxas_inclusas):
    variante = _variante(linha)
    quantidade = max(int(linha.get("quantity") or 1), 1)
    preco = valor_com_fallback(linha, "price", "price_set")
    desconto = _desconto(linha)
    item.variante = variante
    item.produto = variante.produto if variante else None
    tipo_variavel = item.produto and item.produto.tipo == Produto.Tipo.VARIAVEL
    item.id_variacao = variante.pk if tipo_variavel else 0
    item.nome = str(linha.get("title") or linha.get("name") or "")[:255]
    item.sku = str(linha.get("sku") or "")[:100]
    item.quantidade = quantidade
    item.preco_unitario = preco
    item.subtotal, _ = valores_do_item(preco, quantidade)
    item.total = dinheiro(max(item.subtotal - desconto, ZERO))
    item.total_desconto = item.subtotal - item.total
    item.imposto_total = item.imposto_subtotal = _imposto(linha, taxas_inclusas)
    item.requer_entrega = bool(linha.get("requires_shipping", True))
    item.save()
    externo = gid("LineItem", linha.get("id"))
    if externo:
        # A chave e o id do line_item (indice unico referencia_externa_unica).
        ExternalReference.objects.update_or_create(
            platform=Origin.SHOPIFY, entity_type=ENTIDADE, external_id=externo,
            defaults={"object_id": str(item.pk), "origin": Origin.SHOPIFY},
        )
    return item


def _existentes(pedido):
    itens = {str(item.pk): item for item in pedido.itens.all()}
    referencias = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type=ENTIDADE, object_id__in=list(itens))
    return {r.external_id: itens[r.object_id] for r in referencias}


def gravar_itens(pedido, dados):
    """Cria ou atualiza os itens e devolve os servicos contratados de cada um."""
    existentes = _existentes(pedido)
    taxas_inclusas = bool(dados.get("taxes_included"))
    servicos = []
    for linha in dados.get("line_items") or []:
        chave = gid("LineItem", linha.get("id"))
        item = (existentes.get(chave) if chave else None) or ItemPedido(pedido=pedido)
        _gravar(item, linha, taxas_inclusas)
        for servico in servicos_do_item(linha.get("properties")):
            servicos.append({"item_id": item.pk, "sku": item.sku, **servico,
                             "preco": f"{servico['preco']:.2f}"})
    return servicos
