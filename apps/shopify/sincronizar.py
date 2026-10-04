import logging
from functools import partial

from django.db import transaction

from apps.integracoes.falhas import motivo_legivel
from apps.shopify import recursos
from apps.shopify.cliente import ShopifyClient, ShopifyErro
from apps.shopify.consultas import TOPICOS
from apps.shopify.contexto import avisar
from apps.shopify.pedidos_graphql import pedido_graphql_para_rest
from apps.shopify.produtos_busca import completar
from apps.shopify.recursos import SINCRONIZADORES

logger = logging.getLogger(__name__)

# O importador de pedidos le o JSON REST do webhook; a busca vem em GraphQL. Produto
# com variantes ou colecoes cortadas na pagina e buscado inteiro (produtos_busca.py).
CONVERSORES = {"pedidos": pedido_graphql_para_rest, "produtos": completar}

# O progresso grava o sinal de vida (updated_at) e anda a barra. 10 itens levam
# segundos, bem abaixo dos 30 min de TEMPO_SEM_SINAL: recurso grande nao parece
# worker morto, e a barra se mexe sem esperar um lote grande.
SINAL_A_CADA = 10


def recursos_para_buscar(configuracao, recursos=None):
    # Sem escolha (botao antigo, execucao sem parametros) = todos os permitidos. A
    # permissao e conferida de novo aqui: pode ter sido desligada depois da tela.
    return [
        recurso for recurso in SINCRONIZADORES
        if configuracao.habilitado("receber", recurso, "get")
        and (recursos is None or recurso in recursos)
    ]


def _importador(recurso):
    funcao = SINCRONIZADORES[recurso]
    # Importacao e o unico caminho em que o produto da loja manda no do hub; o
    # webhook usa SINCRONIZADORES direto e segue com o nome do hub.
    if funcao is recursos.produto:
        return partial(funcao, sobrescrever=True)
    return funcao


def _erro_da_loja(erro):
    """Erro que afeta todos os itens (credencial, rede): pular so geraria milhares de falhas."""
    texto = str(erro)
    return isinstance(erro, ShopifyErro) and (
        "HTTP 401" in texto or "HTTP 403" in texto or "Nao foi possivel consultar" in texto
    )


def _descricao(dados):
    return dados.get("title") or dados.get("name") or dados.get("email") or ""


def _importar_item(recurso, dados, converter):
    """(obj, criado) do item, ou None se ele falhou: o erro vira falha e a sync segue."""
    try:
        # Savepoint por item: erro de banco de um nao envenena a transacao dos outros.
        with transaction.atomic():
            if converter:
                dados = converter(dados)
            return _importador(recurso)(dados)
    except Exception as erro:  # noqa: BLE001 - item ruim nao pode derrubar os outros
        if _erro_da_loja(erro):
            raise
        logger.exception("Item %s %s nao importado", recurso, dados.get("id"))
        avisar(motivo_legivel(erro), recurso=recurso, id_externo=dados.get("id"),
               descricao=_descricao(dados))
        return None


def _etapa(recurso, feitos, total):
    nome = recurso.capitalize()
    return f"{nome}: {feitos} de {total}" if total is not None else f"{nome}: {feitos} processados"


def sincronizar_loja(configuracao, progresso, recursos=None):
    cliente = ShopifyClient(configuracao)
    recursos = recursos_para_buscar(configuracao, recursos)
    # Com o total de cada recurso a barra anda por item ("Produtos: 350 de 1200"); sem
    # ele (contagem falhou ou nao existe para o recurso) anda por recurso, como antes.
    totais = {recurso: cliente.contar(recurso) for recurso in recursos}
    por_item = bool(recursos) and None not in totais.values()
    geral = sum(totais.values()) if por_item else len(recursos)
    processados = criados = 0
    for posicao, recurso in enumerate(recursos, start=1):
        do_recurso = 0
        # Por item: total geral de itens (item criado na loja durante a busca passaria
        # do total, e o max segura a barra em 100). Por recurso: quantos recursos ja foram.
        feitos, total = (processados, max(geral, processados)) if por_item else (posicao - 1, geral)
        progresso(feitos, total, _etapa(recurso, 0, totais[recurso]))
        converter = CONVERSORES.get(recurso)
        for dados in cliente.listar(recurso):
            resultado = _importar_item(recurso, dados, converter)
            processados += 1
            criados += int(bool(resultado and resultado[1]))
            do_recurso += 1
            if do_recurso % SINAL_A_CADA == 0:
                feitos = processados if por_item else posicao - 1
                progresso(feitos, max(geral, feitos), _etapa(recurso, do_recurso, totais[recurso]))
        if por_item:
            progresso(processados, max(geral, processados),
                      _etapa(recurso, do_recurso, totais[recurso]))
        else:
            progresso(posicao, geral, f"{recurso.capitalize()} sincronizados")
    return f"{processados} itens encontrados; {criados} novos cadastros."


def topicos_habilitados(configuracao):
    for recurso, operacoes in TOPICOS.items():
        for operacao, topico in operacoes.items():
            if configuracao.habilitado("receber", recurso, operacao):
                yield recurso, operacao, topico


def cadastrar_webhooks(configuracao, progresso):
    if not configuracao.url_webhook:
        raise ValueError("Informe a URL publica dos webhooks antes de cadastrar.")
    cliente = ShopifyClient(configuracao)
    topicos = list(topicos_habilitados(configuracao))
    base = configuracao.url_webhook.rstrip("/")
    itens = [(topico, f"{base}/{configuracao.uuid}/{recurso}/") for recurso, _, topico in topicos]
    # O endereco antigo (com o id) entra na limpeza: senao a Shopify mandaria cada evento
    # duas vezes, uma para cada endereco.
    endpoints = {uri.rstrip("/") for _topico, uri in itens} | {
        f"{base}/{configuracao.pk}/{recurso}" for recurso in TOPICOS}
    existentes = [
        webhook for webhook in cliente.listar_webhooks()
        if webhook.get("uri", "").rstrip("/") in endpoints
    ]
    total = len(existentes) + len(itens)
    posicao = 0
    for webhook in existentes:
        cliente.excluir_webhook(webhook["id"])
        posicao += 1
        progresso(posicao, total, f"Removendo webhook {webhook.get('topic', '')}")
    for topico, uri in itens:
        cliente.cadastrar_webhook(topico, uri)
        posicao += 1
        progresso(posicao, total, f"Webhook {topico}")
    if existentes:
        return f"{len(existentes)} webhooks removidos; {len(itens)} cadastrados."
    return f"{len(itens)} webhooks cadastrados."
