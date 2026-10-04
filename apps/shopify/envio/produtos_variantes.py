"""Variantes do hub no formato do Shopify: preco, opcoes, entrada das mutations e vinculo."""

# Sem opcao nenhuma o Shopify usa esta opcao padrao (produto simples).
OPCAO_PADRAO, VALOR_PADRAO = "Title", "Default Title"


def dinheiro(valor):
    # Texto e nao float: "80.00" chega exato ao escalar Money do Shopify.
    return None if valor is None else f"{valor:.2f}"


def precos(variante):
    """(price, compareAtPrice) do Shopify: o preco de venda e o "de" riscado.

    O hub guarda o normal em `price` e a promocao em `sale_price` (o import faz o
    inverso em apps/shopify/produtos.py::_precos).
    """
    venda = variante.current_price
    if venda is not None and variante.price is not None and venda < variante.price:
        return dinheiro(venda), dinheiro(variante.price)
    return dinheiro(venda), dinheiro(variante.compare_at_price)


def opcoes_da_variante(variante, varias):
    opcoes = sorted(
        variante.opcoes.select_related("valor__tipo"),
        key=lambda item: (item.valor.tipo.posicao, item.valor.tipo_id),
    )
    if opcoes:
        return [(item.valor.tipo.nome, item.valor.valor) for item in opcoes]
    # Variavel sem opcoes cadastradas: o titulo diferencia as variantes na loja.
    return [(OPCAO_PADRAO, variante.titulo if varias else VALOR_PADRAO)]


def opcoes_do_produto(por_variante):
    opcoes = {}
    for pares in por_variante:
        for nome, valor in pares:
            valores = opcoes.setdefault(nome, [])
            if valor not in valores:
                valores.append(valor)
    return [
        {"name": nome, "values": [{"name": valor} for valor in valores]}
        for nome, valores in opcoes.items()
    ]


def valores_de_opcao(opcoes):
    return [{"optionName": nome, "name": valor} for nome, valor in opcoes]


def comum(variante):
    """Campos da variante aceitos igualmente por productSet e pelas mutations em lote."""
    preco, comparacao = precos(variante)
    return {
        "price": preco,
        "compareAtPrice": comparacao,
        "barcode": variante.barcode,
        "taxable": variante.taxable,
        "inventoryPolicy": variante.inventory_policy.upper(),
        "inventoryItem": {
            "tracked": variante.manage_inventory,
            "requiresShipping": variante.requires_shipping,
        },
    }


def em_lote(variante):
    """Entrada de productVariantsBulkUpdate/Create: ali nao ha `sku` no topo, so em
    inventoryItem (ProductVariantsBulkInput, 2026-07)."""
    dados = comum(variante)
    dados["inventoryItem"] = {"sku": variante.sku, **dados["inventoryItem"]}
    return dados


def vincular(enviador, variante, recebida, produto_gid):
    """Grava (ou troca) o vinculo da variante com o gid e o inventoryItem da loja."""
    item = (recebida.get("inventoryItem") or {}).get("id") or ""
    # Um vinculo por variante: se a loja recriou a variante (id novo), o antigo sai.
    enviador.referencias_variantes().filter(object_id=str(variante.pk)).exclude(
        external_id=recebida["id"]
    ).delete()
    enviador.referencias_variantes().update_or_create(
        account_id=enviador.configuracao.account_id,
        platform=enviador.plataforma,
        entity_type="variantes",
        external_id=recebida["id"],
        defaults={
            "object_id": str(variante.pk),
            "external_parent_id": produto_gid,
            "metadata": {"inventory_item_id": item},
            "origin": enviador.plataforma,
        },
    )
