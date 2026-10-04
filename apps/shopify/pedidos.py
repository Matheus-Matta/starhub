"""Importa um pedido do Shopify (JSON REST do webhook) para o pedido canonico do hub.

    pedido, criado = importar_pedido(json_do_webhook_orders_create)

A sincronizacao (GraphQL) converte para este mesmo formato REST e chama aqui:
uma porta de entrada so, para o pedido nascer igual pelos dois caminhos.
O mesmo pedido chegando de novo (reenvio ou orders/updated) atualiza, nao duplica.
"""

from django.db import IntegrityError, transaction

from apps.core.models import ExternalReference, Origin
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Pedido
from apps.loja.services.extras_pedido import mesclar_extras
from apps.loja.totais import recalcular_totais
from apps.shopify.pedidos_base import data, ids_do_pedido
from apps.shopify.pedidos_cliente import cliente_do_pedido
from apps.shopify.pedidos_cupons import gravar_cupons
from apps.shopify.pedidos_enderecos import documento, gravar_enderecos, tipo_pessoa
from apps.shopify.pedidos_entrega import entrega_do_pedido, gravar_frete
from apps.shopify.pedidos_itens import gravar_itens
from apps.shopify.pedidos_status import aplicar_status, gravar_pagamento
from apps.shopify.recursos import _existente, _referenciar


def _numero(dados, numero_externo):
    return str(dados.get("name") or dados.get("order_number") or numero_externo).lstrip("#")


def _pelo_rastro(externo):
    # Pedido gravado antes do vinculo existir: o gid do Shopify ficou em source_reference.
    return Pedido.objects.filter(source_name="shopify", source_reference=externo).first()


def _pedido_da_linha(dados, externo, numero_externo):
    """Acha (pelo vinculo) ou cria a linha do pedido, sempre com numero do hub.

    O numero da loja vai para external_number. Quem segura dois webhooks simultaneos
    e o indice unico do vinculo (referencia_externa_unica): o segundo desfaz o pedido
    que criou e usa o do primeiro.
    """
    obj = _existente("pedidos", externo) or _pelo_rastro(externo)
    if obj is not None:
        return _referenciar("pedidos", externo, obj), False
    try:
        with transaction.atomic():
            obj = Pedido.objects.create(
                external_number=_numero(dados, numero_externo), source_reference=externo,
                origin=Origin.SHOPIFY, source_name="shopify",
            )
            ExternalReference.objects.create(
                platform=Origin.SHOPIFY, entity_type="pedidos", external_id=externo,
                object_id=str(obj.pk), origin=Origin.SHOPIFY,
            )
    except IntegrityError:
        vinculo = ExternalReference.objects.get(
            platform=Origin.SHOPIFY, entity_type="pedidos", external_id=externo
        )
        return Pedido.objects.get(pk=vinculo.object_id), False
    return obj, True


def _url_admin(loja, numero_externo):
    if loja is None:
        loja = (ConfiguracaoIntegracao.objects.filter(plataforma="shopify")
                .values_list("dominio_loja", flat=True).first()) or ""
    loja = loja.strip().removeprefix("https://").removeprefix("http://").strip("/")
    return f"https://{loja}/admin/orders/{numero_externo}" if loja else ""


def _campos_do_pedido(pedido, dados, externo, numero_externo):
    cobranca = dados.get("billing_address") or {}
    pedido.external_number = _numero(dados, numero_externo)
    pedido.email = (dados.get("email") or dados.get("contact_email") or pedido.email)[:254]
    pedido.telefone = str(dados.get("phone") or cobranca.get("phone") or pedido.telefone)[:30]
    pedido.moeda = dados.get("currency") or dados.get("presentment_currency") or pedido.moeda
    pedido.observacao_cliente = dados.get("note") or ""
    pedido.placed_at = data(dados.get("created_at")) or pedido.placed_at
    pedido.source_name, pedido.source_reference = "shopify", externo
    pedido.cliente = cliente_do_pedido(dados) or pedido.cliente


def _extras(dados, numero_externo, loja, cupons, servicos):
    doc = documento(dados)
    return {
        "origem": {
            "canal": "shopify", "id": numero_externo,
            "numero": str(dados.get("order_number") or ""), "nome": dados.get("name"),
            "url": _url_admin(loja, numero_externo),
            "status_financeiro": dados.get("financial_status"),
            "atualizado_em": dados.get("updated_at"),
        },
        "cliente": {"cpf": doc, "tipo_pessoa": tipo_pessoa(doc)},
        "entrega": entrega_do_pedido(dados),
        "cupons": cupons,
        "servicos": servicos,
    }


@transaction.atomic
def importar_pedido(dados, loja=None):
    """`loja`: dominio da loja Shopify para o link do admin; sem ele, o da configuracao."""
    externo, numero_externo = ids_do_pedido(dados)
    pedido, criado = _pedido_da_linha(dados, externo, numero_externo)
    # Lock e releitura: o que foi lido antes do lock pode ser de outro webhook.
    pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)
    _campos_do_pedido(pedido, dados, externo, numero_externo)
    aplicar_status(pedido, dados)
    gravar_enderecos(pedido, dados)
    gravar_frete(pedido, dados)
    cupons = gravar_cupons(pedido, dados)
    pedido.save()
    servicos = gravar_itens(pedido, dados)
    mesclar_extras(pedido, _extras(dados, numero_externo, loja, cupons, servicos))
    pedido.save(update_fields=["metadados", "updated_at"])
    recalcular_totais(pedido)
    gravar_pagamento(pedido, dados, numero_externo)
    return pedido, criado
