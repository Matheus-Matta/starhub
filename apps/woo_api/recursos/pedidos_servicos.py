"""Servicos do pedido na borda da API: no line_item, nao no meta do pedido.

O banco guarda os servicos num lugar so, pedido.metadados["starhub"]["servicos"],
cada um com item_id e sku (e o que o Shopify e o EPOFW gravam). O ERP liga o
servico ao produto, entao a API mostra cada servico no item dele:

    line_items[].meta_data: {"key": "starhub", "value": {"servicos": [
        {"servico": "Montagem", "opcao": "Sim", "preco": "80.00"}]}}

Ao lado sai o mesmo servico no formato EPOFW (pedidos_epofw.py), que e o que o
ERP le. item_id e sku ficam de fora porque o item ja os tem. Na volta (PUT) o mesmo
formato e aceito e vira servico daquele item, sem guardar o "starhub" cru no
metadados do item: assim o ERP pode reenviar o que recebeu sem duplicar nada.
"""

from apps.loja.services.extras_pedido import CHAVE, extras
from apps.woo_api.erros import parametro_invalido
from apps.woo_api.recursos.pedidos_epofw import metas_epofw
from apps.woo_api.recursos.pedidos_meta import servico_valido

_DO_ITEM = ("item_id", "sku")


def servicos_por_item(pedido):
    """{item_id: [servico sem item_id/sku]} lido do que o pedido guarda."""
    por_item = {}
    for servico in extras(pedido).get("servicos") or []:
        if isinstance(servico, dict):
            limpo = {k: v for k, v in servico.items() if k not in _DO_ITEM}
            por_item.setdefault(servico.get("item_id"), []).append(limpo)
    return por_item


def meta_do_pedido(lista):
    """meta_data do pedido sem a secao servicos; starhub vazio nao sai."""
    saida = []
    for meta in lista or []:
        if meta.get("key") == CHAVE and isinstance(meta.get("value"), dict):
            valor = {k: v for k, v in meta["value"].items() if k != "servicos"}
            if not valor:
                continue
            meta = {**meta, "value": valor}
        saida.append(meta)
    return saida


def meta_do_item(item, servicos):
    """meta_data do item com starhub e EPOFW montados na hora a partir dos servicos."""
    lista = item.metadados or []
    # Um "starhub" gravado no item por versao antiga nao e a fonte: o pedido e.
    saida = [dict(meta) for meta in lista if meta.get("key") != CHAVE]
    if servicos:
        proximo = max((meta.get("id", 0) for meta in lista), default=0) + 1
        saida.append({"id": proximo, "key": CHAVE, "value": {"servicos": servicos}})
        saida.extend(metas_epofw(item, servicos, proximo + 1))
    return saida


def separar_starhub(meta_data):
    """Tira o "starhub" do meta_data do item: (servicos sem item_id, resto).

    servicos e None quando o item nao trouxe starhub.servicos: ai os servicos ja
    gravados continuam. Lista vazia tira os servicos do item.
    """
    if not isinstance(meta_data, list):
        return None, meta_data
    servicos, resto = None, []
    for meta in meta_data:
        if not (isinstance(meta, dict) and meta.get("key") == CHAVE):
            resto.append(meta)
            continue
        valor = meta.get("value")
        if not isinstance(valor, dict):
            raise parametro_invalido("line_items", 'O value de "starhub" do item deve ser um '
                                     'objeto, por exemplo {"servicos": [...]}.')
        if "servicos" not in valor:
            continue
        if not isinstance(valor["servicos"], list):
            raise parametro_invalido("line_items", '"servicos" do item deve ser uma lista; '
                                     'mande [] para tirar os servicos do item.')
        servicos = [{k: v for k, v in servico_valido(s).items() if k not in _DO_ITEM}
                    for s in valor["servicos"]]
    return servicos, resto

