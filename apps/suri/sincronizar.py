"""Busca o Suri Shop (tela Sincronizar loja) e importa no hub.

Ordem: categorias (a arvore inteira numa chamada), produtos, estoque e pedidos (o
item do pedido acha o produto pelo vinculo, sem ir de novo ao Suri). Na importacao o
Suri manda no texto do produto. Pedidos: os dos ultimos 30 dias (padrao da API).
"""

import logging

from django.db import transaction

from apps.integracoes.falhas import motivo_legivel
from apps.loja.models import Produto, VarianteProduto
from apps.suri import vinculos
from apps.suri.cliente import SuriClient, SuriErro
from apps.suri.contexto import avisar
from apps.suri.importar_catalogo import importar_categorias, importar_produto
from apps.suri.importar_pedidos import PedidoIgnorado, importar_pedido

logger = logging.getLogger(__name__)
RECURSOS = ("categorias", "produtos", "estoque", "pedidos")
SINAL_A_CADA = 10


def recursos_para_buscar(configuracao, escolhidos=None):
    return [recurso for recurso in RECURSOS
            if configuracao.habilitado("receber", recurso, "get")
            and (escolhidos is None or recurso in escolhidos)]


def atualizar_estoque(dados):
    """So a quantidade das variantes ja vinculadas; o estoque nunca cria cadastro."""
    if vinculos.objeto_id("produtos", dados.get("id")) is None:
        return None, False
    for dimensao in dados.get("dimensions") or []:
        chave = vinculos.id_variacao(dados["id"], dimensao.get("sku"))
        variante = vinculos.existente("variantes", VarianteProduto, chave)
        if variante is not None:
            variante.inventory_quantity = int(sum(
                (loja or {}).get("stock") or 0 for loja in (dimensao.get("stocks") or {}).values()))
            variante.save()  # save(), nao update(): o Produto recalcula a situacao do estoque
    return vinculos.existente("produtos", Produto, dados["id"]), False


def _importar_item(recurso, importar, dados):
    try:
        # Savepoint por item: erro de banco de um nao envenena a transacao dos outros.
        with transaction.atomic():
            return importar(dados)
    except PedidoIgnorado:
        return None
    except Exception as erro:  # noqa: BLE001 - item ruim nao pode derrubar os outros
        if isinstance(erro, SuriErro) and erro.status in (None, 401, 403):
            raise  # credencial ou rede: afeta todos os itens
        logger.exception("Item %s %s nao importado", recurso, dados.get("id"))
        avisar(motivo_legivel(erro), recurso=recurso, id_externo=dados.get("id"),
               descricao=dados.get("name") or dados.get("friendlyCode") or "")
        return None


def sincronizar_loja(configuracao, progresso, recursos=None):
    cliente = SuriClient(configuracao)
    recursos = recursos_para_buscar(configuracao, recursos)
    importadores = {
        "produtos": lambda dados: importar_produto(dados, sobrescrever=True),
        "estoque": atualizar_estoque,
        "pedidos": importar_pedido,
    }
    processados = criados = 0
    for posicao, recurso in enumerate(recursos):
        # A API nao conta os itens antes: a barra anda por recurso, a etapa conta os itens.
        progresso(posicao, len(recursos), f"{recurso.capitalize()}: buscando")
        if recurso == "categorias":
            mapa = importar_categorias(cliente.get("shop/categories"))
            processados += len(mapa)
            continue
        itens = cliente.pedidos() if recurso == "pedidos" else cliente.produtos()
        do_recurso = 0
        for dados in itens:
            resultado = _importar_item(recurso, importadores[recurso], dados)
            processados, do_recurso = processados + 1, do_recurso + 1
            criados += int(bool(resultado and resultado[1]))
            if do_recurso % SINAL_A_CADA == 0:
                progresso(posicao, len(recursos),
                          f"{recurso.capitalize()}: {do_recurso} processados")
    progresso(len(recursos), len(recursos), "Concluido")
    return f"{processados} itens encontrados; {criados} novos cadastros."
