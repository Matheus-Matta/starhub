"""Servicos do pedido na borda da API: no line_item, nao no meta do pedido.

O banco guarda os servicos num lugar so, pedido.metadados["starhub"]["servicos"],
cada um com item_id, o sku do item e o servico_id do cadastro de Servicos. O ERP
liga o servico ao produto, entao a API mostra cada servico no item dele, com o id
e o SKU do cadastro (o que o ERP usa para reconhecer o servico):

    line_items[].meta_data: {"key": "starhub", "value": {"servicos": [
        {"id": 3, "nome": "Montagem", "sku": "SERV-MONTAGEM", "preco": "80.00",
         "opcao": "Sim"}]}}

Ao lado sai o mesmo servico no formato EPOFW (pedidos_epofw.py), que e o que o
ERP antigo le. Na volta (PUT) o mesmo formato e aceito ("nome", ou "servico" do
formato anterior) e vira servico daquele item; id e sku vem do cadastro, nao do
corpo, entao o ERP pode reenviar o que recebeu sem duplicar nem trocar nada.
"""

from apps.loja.services.extras_pedido import CHAVE, extras
from apps.loja.services.servicos import cadastros, do_cadastro
from apps.woo_api.erros import parametro_invalido
from apps.woo_api.recursos.pedidos_epofw import metas_epofw
from apps.woo_api.recursos.pedidos_meta import servico_valido

# Vem do cadastro ou do item, nunca do corpo da requisicao.
_DERIVADOS = ("item_id", "sku", "id", "servico_id", "nome")


def _para_erp(servico, cadastro):
    return {
        "id": cadastro.pk if cadastro else None,
        "nome": cadastro.nome if cadastro else servico.get("servico"),
        "sku": cadastro.sku if cadastro else "",
        "preco": servico.get("preco"),
        "opcao": servico.get("opcao"),
    }


def servicos_por_item(pedido):
    """{item_id: [servico no formato do ERP]} lido do que o pedido guarda."""
    guardados = [s for s in extras(pedido).get("servicos") or [] if isinstance(s, dict)]
    mapa = cadastros(guardados)
    por_item = {}
    for servico in guardados:
        por_item.setdefault(servico.get("item_id"), []).append(
            _para_erp(servico, do_cadastro(servico, mapa)))
    return por_item


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


def _do_corpo(servico):
    servico = servico_valido(servico)
    nome = servico.get("nome") or servico.get("servico")
    return {**{k: v for k, v in servico.items() if k not in _DERIVADOS}, "servico": nome}


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
        servicos = [_do_corpo(s) for s in valor["servicos"]]
    return servicos, resto
