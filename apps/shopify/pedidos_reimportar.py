"""Busca de novo no Shopify os pedidos escolhidos e passa pelo importador de sempre.

Para pedido que ficou errado no hub (ex.: gravado sem itens por uma versao antiga, e
o ERP via "total calculado R$ 0,00"): itens, totais, status e enderecos voltam a ser
os da loja. So leitura no Shopify; a gravacao e no hub. Pedido desativado no hub fica
como esta (pedidos_ativos.ignorar_entrada).

    reimportar(configuracao, progresso, pedidos=[96, 97])
"""

from apps.core.models import ExternalReference, Origin
from apps.shopify.cliente import ShopifyClient
from apps.shopify.consultas import CONSULTAS
from apps.shopify.contexto import avisar
from apps.shopify.pedidos import importar_pedido
from apps.shopify.pedidos_documento_lote import consultar_com_espera
from apps.shopify.pedidos_graphql import pedido_graphql_para_rest

# Mesmos campos da sincronizacao (consultas.py), por id: o pedido nasce igual pelos dois
# caminhos. 3 por consulta, como la: cada pedido com 50 itens custa ~300 pontos.
LOTE = 3
_ORDERS = CONSULTAS["pedidos"][1]
_FRAGMENTOS = _ORDERS[:_ORDERS.index("query(")]
_CAMPOS = _ORDERS[_ORDERS.index("nodes {") + len("nodes {"):_ORDERS.rindex("pageInfo")]
CONSULTA = (_FRAGMENTOS + "query ($ids: [ID!]!) { nodes(ids: $ids) { ... on Order {"
            + _CAMPOS.rstrip().removesuffix("}") + "} } }")


def _gids(pedidos):
    vinculos = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type="pedidos",
        object_id__in=[str(pk) for pk in pedidos]).values_list("object_id", "external_id")
    return sorted((int(pk), gid) for pk, gid in vinculos)


def reimportar(configuracao, progresso, pedidos):
    alvos = _gids(pedidos)
    total, feitos, sumidos = len(alvos), 0, 0
    cliente = ShopifyClient(configuracao)
    progresso(0, total, f"Pedidos: 0 de {total}")
    for inicio in range(0, total, LOTE):
        lote = {gid: pk for pk, gid in alvos[inicio:inicio + LOTE]}
        achados = set()
        for no in consultar_com_espera(cliente, CONSULTA, list(lote)):
            if not no or no.get("id") not in lote:
                continue
            achados.add(no["id"])
            try:
                importar_pedido(pedido_graphql_para_rest(no), configuracao.dominio_loja)
                feitos += 1
            except Exception as erro:  # noqa: BLE001 - um pedido ruim nao para o lote
                avisar(f"Pedido nao reimportado: {erro}", recurso="pedidos",
                       id=lote[no["id"]], descricao=no.get("name") or "", id_externo=no["id"])
        for gid in set(lote) - achados:  # nodes devolve null para pedido apagado na loja
            sumidos += 1
            avisar("O pedido nao existe mais no Shopify: nada foi alterado.",
                   recurso="pedidos", id=lote[gid], id_externo=gid)
        andou = min(inicio + LOTE, total)
        progresso(andou, total, f"Pedidos: {andou} de {total}")
    sem_vinculo = len(set(pedidos)) - total
    return (f"{total} pedido(s) buscados no Shopify: {feitos} reimportado(s), {sumidos} "
            f"nao existem mais na loja, {sem_vinculo} sem vinculo com o Shopify.")
