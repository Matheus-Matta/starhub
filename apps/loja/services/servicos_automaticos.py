"""Servico que entra sozinho no pedido (Servico.inclusao "regra" ou "todos").

    Montagem gratis, "todos": pedido com guarda-roupa (2 un.) e mesa
    -> starhub.servicos ganha {"item_id": <guarda-roupa>, "servico": "Montagem",
       "preco": "0.00", "automatico": True} e o mesmo para a mesa.

O preco e o da regra que pega o produto (ou o padrao do servico) vezes a quantidade,
mas NAO soma no item: o cliente nao pagou o servico na loja e o total do pedido tem
que bater com o dela. Por isso o servico nao leva "somado" (pedido legado no WooCommerce).
A parte automatica e refeita a cada importacao: o webhook reimporta o pedido e um item
pode ter saido. Servico que o cliente ja escolheu no item nao repete.
"""

from apps.loja.dinheiro import dinheiro
from apps.loja.models import Servico
from apps.loja.services.extras_pedido import extras, mesclar_extras


def _automaticos():
    return list(Servico.objects.filter(active=True).exclude(
        inclusao=Servico.Inclusao.ESCOLHA).order_by("nome", "pk"))


def _do_item(item, automaticos, escolhidos):
    das_regras = dict(item.produto.servicos) if item.produto_id else {}
    for servico in automaticos:
        if (item.pk, servico.pk) in escolhidos:
            continue
        if servico not in das_regras and servico.inclusao != Servico.Inclusao.TODOS:
            continue
        preco = dinheiro(das_regras.get(servico, servico.preco) * item.quantidade)
        yield {"item_id": item.pk, "sku": item.sku, "servico": servico.nome,
               "servico_id": servico.pk, "opcao": "Sim", "preco": f"{preco:.2f}",
               "automatico": True}


def completar(pedido):
    """Grava em starhub.servicos os servicos automaticos de cada item do pedido."""
    atuais = extras(pedido).get("servicos") or []
    servicos = [s for s in atuais if not (isinstance(s, dict) and s.get("automatico"))]
    automaticos = _automaticos()
    if automaticos:
        escolhidos = {(s.get("item_id"), s.get("servico_id"))
                      for s in servicos if isinstance(s, dict)}
        for item in pedido.itens.select_related("produto").order_by("pk"):
            servicos.extend(_do_item(item, automaticos, escolhidos))
    if servicos == atuais:
        return
    mesclar_extras(pedido, {"servicos": servicos})
    pedido.save(update_fields=["metadados", "updated_at"])
