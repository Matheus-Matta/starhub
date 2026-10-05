"""Busca a loja WooCommerce inteira (tela Sincronizar loja) e importa no hub.

A ordem importa: categoria antes do produto (o produto aponta para ela), produto e
cliente antes do pedido (o item e o comprador sao achados pelo vinculo, sem ir de
novo a loja). Na importacao a loja manda no texto do produto e do cliente.
"""

import logging

from django.db import transaction

from apps.integracoes.falhas import motivo_legivel
from apps.woocommerce.cliente import WooClient, WooErro
from apps.woocommerce.contexto import avisar
from apps.woocommerce.estoque import atualizar_estoque
from apps.woocommerce.importar_catalogo import importar_categoria
from apps.woocommerce.importar_clientes import importar_cliente
from apps.woocommerce.importar_cupons import importar_cupom
from apps.woocommerce.importar_pedidos import importar_pedido
from apps.woocommerce.sincronizar_produtos import importar_completo

logger = logging.getLogger(__name__)
SINAL_A_CADA = 10  # mesmo ritmo do Shopify: a barra anda e a tarefa nao parece morta

# recurso do hub -> (rota da API, filtros da listagem)
ROTAS = {
    "categorias": ("products/categories", {}),
    "produtos": ("products", {}),
    # Sem role=all a API devolve so quem tem o papel "customer" (assinante fica de fora).
    "clientes": ("customers", {"role": "all"}),
    "cupons": ("coupons", {}),
    "pedidos": ("orders", {}),
    "estoque": ("products", {}),
}


def recursos_para_buscar(configuracao, escolhidos=None):
    return [recurso for recurso in ROTAS
            if configuracao.habilitado("receber", recurso, "get")
            and (escolhidos is None or recurso in escolhidos)]


def importadores(cliente, configuracao, categorias):
    return {
        "categorias": lambda dados: importar_categoria(dados, categorias),
        "produtos": lambda dados: importar_completo(cliente, dados, sobrescrever=True),
        "clientes": lambda dados: importar_cliente(dados, sobrescrever=True),
        "cupons": importar_cupom,
        "pedidos": lambda dados: importar_pedido(dados, configuracao.dominio_loja),
        "estoque": lambda dados: atualizar_estoque(cliente, dados),
    }


def _erro_da_loja(erro):
    """Credencial ou rede: afeta todos os itens, pular so geraria milhares de falhas."""
    return isinstance(erro, WooErro) and erro.status in (None, 401, 403)


def _importar_item(recurso, importar, dados):
    try:
        # Savepoint por item: erro de banco de um nao envenena a transacao dos outros.
        with transaction.atomic():
            return importar(dados)
    except Exception as erro:  # noqa: BLE001 - item ruim nao pode derrubar os outros
        if _erro_da_loja(erro):
            raise
        logger.exception("Item %s %s nao importado", recurso, dados.get("id"))
        avisar(motivo_legivel(erro), recurso=recurso, id_externo=dados.get("id"),
               descricao=dados.get("name") or dados.get("code") or dados.get("email") or
               dados.get("number") or "")
        return None


def _etapa(recurso, feitos, total):
    nome = recurso.capitalize()
    return f"{nome}: {feitos} de {total}" if total is not None else f"{nome}: {feitos} processados"


def sincronizar_loja(configuracao, progresso, recursos=None):
    cliente = WooClient(configuracao)
    recursos = recursos_para_buscar(configuracao, recursos)
    totais = {recurso: cliente.contar(ROTAS[recurso][0], **ROTAS[recurso][1])
              for recurso in recursos}
    geral = sum(total or 0 for total in totais.values())
    # A categoria pai pode vir depois da filha na lista: todas ficam a mao por id.
    categorias = ({c["id"]: c for c in cliente.listar("products/categories")}
                  if "categorias" in recursos else {})
    funcoes = importadores(cliente, configuracao, categorias)
    processados = criados = 0
    for recurso in recursos:
        rota, filtros = ROTAS[recurso]
        do_recurso = 0
        progresso(processados, max(geral, processados), _etapa(recurso, 0, totais[recurso]))
        itens = categorias.values() if recurso == "categorias" else cliente.listar(rota, **filtros)
        for dados in itens:
            resultado = _importar_item(recurso, funcoes[recurso], dados)
            processados, do_recurso = processados + 1, do_recurso + 1
            criados += int(bool(resultado and resultado[1]))
            if do_recurso % SINAL_A_CADA == 0:
                progresso(processados, max(geral, processados),
                          _etapa(recurso, do_recurso, totais[recurso]))
        progresso(processados, max(geral, processados),
                  _etapa(recurso, do_recurso, totais[recurso]))
    return f"{processados} itens encontrados; {criados} novos cadastros."
