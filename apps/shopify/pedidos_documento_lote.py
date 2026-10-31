"""Busca em lote o CPF/CNPJ do checkout para pedidos do Shopify que chegaram sem.

Os pedidos importados antes de pedidos_documento.py existir vieram sem documento;
esta tarefa consulta o Shopify de LOTE em LOTE e preenche o billing do pedido e o
cadastro do cliente (so o que esta vazio: nada que o operador corrigiu e trocado).
O antes/depois de cada endereco e cliente fica no historico (auditlog).

    preencher_documentos(configuracao, progresso, pedidos=[12, 15])  # ou None = todos
"""

import time

from django.db import transaction

from apps.core.models import ExternalReference, Origin
from apps.loja.models import Pedido
from apps.loja.services.extras_pedido import mesclar_extras
from apps.loja.services.pedidos import gravar_endereco_do_pedido
from apps.loja.validators import somente_digitos
from apps.shopify.cliente import ShopifyClient, ShopifyErro
from apps.shopify.contexto import avisar
from apps.shopify.pedidos_documento import (
    CHAVE,
    VERSAO_DOCUMENTO,
    documento_localizado,
    gravar_documento_do_cliente,
)
from apps.shopify.pedidos_enderecos import tipo_pessoa

# 20 pedidos x localizationExtensions(first: 10) fica perto de 300 pontos de custo,
# longe do limite de 1000 por consulta do Shopify.
LOTE = 20
TENTATIVAS = 5
CONSULTA_LOTE = """
  query ($ids: [ID!]!) { nodes(ids: $ids) { ... on Order { id name
    localizationExtensions(first: 10) { nodes { purpose countryCode title value } } } } }
"""


def pedidos_sem_documento(pedidos=None):
    """Pedidos do Shopify cujo billing nao tem CPF nem CNPJ, com o gid de cada um."""
    qs = Pedido.objects.filter(origin=Origin.SHOPIFY).exclude(
        endereco_cobranca__document__gt="")
    if pedidos is not None:
        qs = qs.filter(pk__in=pedidos)
    ids = {str(pk) for pk in qs.values_list("pk", flat=True)}
    vinculos = ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type="pedidos", object_id__in=ids,
    ).values_list("object_id", "external_id")
    return sorted((int(pk), gid) for pk, gid in vinculos)


def _consultar(cliente, gids):
    """nodes(ids) com espera quando o Shopify limita a taxa (THROTTLED)."""
    for tentativa in range(TENTATIVAS):
        try:
            return cliente.graphql(CONSULTA_LOTE, {"ids": gids}).get("nodes") or []
        except ShopifyErro as erro:
            if "throttled" not in str(erro).casefold() or tentativa == TENTATIVAS - 1:
                raise
            time.sleep(2 ** tentativa)
    return []


@transaction.atomic
def _preencher(pedido_id, doc, nome):
    # Lock e releitura: um webhook do mesmo pedido pode ter gravado o CPF no meio.
    pedido = Pedido.objects.select_for_update().select_related(
        "endereco_cobranca", "cliente").get(pk=pedido_id)
    if pedido.endereco_cobranca and pedido.endereco_cobranca.document:
        return False
    campo = "cnpj" if len(doc) == 14 else "cpf"
    gravar_endereco_do_pedido(pedido, "billing", {campo: doc, "persontype": tipo_pessoa(doc)})
    mesclar_extras(pedido, {"cliente": {"cpf": doc, "tipo_pessoa": tipo_pessoa(doc)}})
    pedido.save(update_fields=["endereco_cobranca", "metadados", "updated_at"])
    gravar_documento_do_cliente(pedido.cliente, doc, nome)
    return True


def preencher_documentos(configuracao, progresso, pedidos=None):
    alvos = pedidos_sem_documento(pedidos)
    total, preenchidos, sem_documento = len(alvos), 0, 0
    cliente = ShopifyClient(configuracao, versao=VERSAO_DOCUMENTO)
    progresso(0, total, f"Pedidos sem CPF: 0 de {total}")
    for inicio in range(0, total, LOTE):
        lote = dict((gid, pk) for pk, gid in alvos[inicio:inicio + LOTE])
        for no in _consultar(cliente, list(lote)):
            if not no or no.get("id") not in lote:
                continue  # pedido apagado na loja: nodes devolve null
            doc = somente_digitos(documento_localizado(
                {CHAVE: (no.get("localizationExtensions") or {}).get("nodes")}))
            if len(doc) not in (11, 14):
                sem_documento += 1
                continue
            try:
                preenchidos += _preencher(lote[no["id"]], doc, no.get("name") or "")
            except Exception as erro:  # noqa: BLE001 - um pedido ruim nao para o lote
                avisar(f"CPF nao gravado: {erro}", recurso="pedidos", id=lote[no["id"]],
                       descricao=no.get("name") or "", id_externo=no["id"])
        feitos = min(inicio + LOTE, total)
        progresso(feitos, total, f"Pedidos sem CPF: {feitos} de {total}")
    return (f"{total} pedido(s) do Shopify sem CPF verificados: {preenchidos} preenchido(s), "
            f"{sem_documento} sem CPF no checkout da loja.")
