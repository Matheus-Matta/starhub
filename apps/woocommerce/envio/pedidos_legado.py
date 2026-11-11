"""Pedido do hub -> POST orders no WooCommerce, no formato padrao ou no legado.

O corpo e o do GET da API Woo do hub (apps/woo_api/recursos/pedidos_saida.py), so com o
que o POST aceita. O switch "pedido no formato legado" da configuracao escolhe:

- padrao (desligado): itens com os valores como o hub guarda (servico ja somado no
  item) e os servicos tambem no meta do item;
- legado (ligado): o valor do servico que o hub somou no item ("somado") sai do
  subtotal e do total do item e vai como linha de taxa ("Montagem (Sofa)" 80.00). O
  total do pedido continua com o servico e ele conta uma vez so: o Woo soma itens +
  taxas. Sem EPOFW: o ERP somaria o epofw_price em cima da taxa. Servico so informado
  pela loja (sem "somado") nao vira taxa: o cliente nao pagou por ele.

Nos dois:
- cada item com o produto/variacao da loja (vinculo) e a quantidade;
- meta do pedido "starhub" (origem, cliente, entrega.agendamento dd-mm-aaaa, cupons,
  idVendedor); frete e taxas como linhas; sem coupon_lines, porque o Woo aplicaria o
  cupom de novo sobre itens que ja vem com o desconto.
"""

from decimal import Decimal

from apps.loja.dinheiro import texto
from apps.loja.services.extras_pedido import extras, somados_por_item
from apps.woo_api.recursos.pedidos_saida import pedido_para_woo
from apps.woocommerce import vinculos

# Marca do pedido criado pelo hub: a importacao do Woo (webhook order.*, sincronizacao)
# o ignora; senao o eco duplicava o pedido ou trocava os valores do hub pelos da loja.
META_DO_HUB = "starhub_pedido"
STATUS_WOO = {"pending", "processing", "on-hold", "completed", "cancelled", "refunded",
              "failed"}


def _sem_id(metas):
    # O "id" do meta e do banco de quem le; no POST o Woo cria os dele.
    return [{"key": m["key"], "value": m["value"]} for m in metas or []]


def _item(item, saida, fora):
    linha = {"name": item.nome, "quantity": item.quantidade,
             "subtotal": texto(Decimal(saida["subtotal"]) - fora),
             "total": texto(Decimal(saida["total"]) - fora),
             "meta_data": _sem_id(saida["meta_data"])}
    produto = vinculos.externo_id("produtos", item.produto_id) if item.produto_id else None
    if produto:
        linha["product_id"] = int(produto)
        variacao = vinculos.externo_id("variantes", item.variante_id) if item.id_variacao else None
        if variacao:
            linha["variation_id"] = int(variacao)
    elif item.sku:
        # Sem o produto na loja o Woo grava a linha so com o nome: o SKU vai no meta.
        linha["meta_data"].append({"key": "sku", "value": item.sku})
    return linha


def taxas_dos_servicos(pedido, itens):
    """Uma taxa por servico somado, no mesmo valor que saiu do item (somados_por_item)."""
    taxas = []
    for servico in extras(pedido).get("servicos") or []:
        item = itens.get(servico.get("item_id")) if isinstance(servico, dict) else None
        # Item que saiu do pedido nao tem o valor do servico: a taxa aumentaria o total.
        if item is None or not servico.get("somado"):
            continue
        nome = servico.get("servico") or servico.get("nome") or "Servico"
        taxas.append({"name": f"{nome} ({item.nome})",
                      "total": texto(Decimal(str(servico.get("preco") or "0"))),
                      "tax_status": "none"})
    return taxas


def corpo(pedido, legado):
    saida = pedido_para_woo(pedido, servico_no_item=True)
    fora = somados_por_item(pedido) if legado else {}
    itens = {item.pk: item for item in pedido.itens.all()}
    cliente = vinculos.externo_id("clientes", pedido.cliente_id) if pedido.cliente_id else None
    corpo = {
        "currency": saida["currency"], "customer_id": int(cliente) if cliente else 0,
        "billing": saida["billing"], "shipping": saida["shipping"],
        "payment_method": saida["payment_method"],
        "payment_method_title": saida["payment_method_title"],
        "transaction_id": saida["transaction_id"], "customer_note": saida["customer_note"],
        "set_paid": False,  # o status vem do hub; set_paid mudaria para "processing"
        "meta_data": [*_sem_id(saida["meta_data"]),
                      {"key": META_DO_HUB, "value": str(pedido.uuid)}],
        "line_items": [_item(itens[linha["id"]], linha, fora.get(linha["id"], Decimal("0")))
                       for linha in saida["line_items"]],
        "shipping_lines": [{"method_id": f.get("method_id", ""),
                            "method_title": f.get("method_title", ""), "total": f.get("total")}
                           for f in saida["shipping_lines"]],
        "fee_lines": [{"name": t.get("name", ""), "total": t.get("total"),
                       "tax_status": "none"} for t in saida["fee_lines"]]
                     + (taxas_dos_servicos(pedido, itens) if legado else []),
    }
    if pedido.status in STATUS_WOO:
        corpo["status"] = pedido.status
    return corpo
