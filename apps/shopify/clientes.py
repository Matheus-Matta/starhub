"""Customer do Shopify -> Cliente do hub: cadastro, enderecos, marketing e pagante.

O que o hub tem como coluna (telefone, notas, marketing, idioma...) vai para o
Cliente; o que so o Shopify conhece (contadores, tags, estado da conta) fica no
metadata do vinculo. Le o formato da busca GraphQL; o webhook REST chega aqui ja
convertido por clientes_webhook.de_webhook.

    importar_cliente: cliente novo recebe tudo; o que ja existia so e completado
    atualizar_cliente: webhook customers/update; o Shopify sobrescreve o que mandou
"""

from datetime import UTC

from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.core.models import ExternalReference, Origin
from apps.loja.dinheiro import ValorInvalido, dinheiro
from apps.loja.models import Cliente, Pedido
from apps.shopify.clientes_enderecos import sincronizar_enderecos, telefone_ou_vazio

ENTIDADE = "clientes"
INSCRITO = "SUBSCRIBED"


def _email(dados):
    email = (dados.get("defaultEmailAddress") or {}).get("emailAddress") or dados.get("email")
    return (email or "").strip()


def _campos(dados):
    """Campos do Cliente presentes em `dados`. Chave ausente nao mexe no hub: o
    pedido manda so nome e telefone, e isso nao pode apagar notas nem marketing."""
    campos = {}
    if "firstName" in dados:
        campos["nome"] = (dados.get("firstName") or "")[:150]
    if "lastName" in dados:
        campos["sobrenome"] = (dados.get("lastName") or "")[:150]
    if "defaultPhoneNumber" in dados or "phone" in dados:
        bruto = (dados.get("defaultPhoneNumber") or {}).get("phoneNumber") or dados.get("phone")
        campos["telefone"] = telefone_ou_vazio(bruto)
    if "note" in dados:
        campos["notas"] = dados.get("note") or ""
    if dados.get("locale"):
        campos["locale"] = dados["locale"][:10]
    if "taxExempt" in dados:
        campos["isento_imposto"] = bool(dados.get("taxExempt"))
    if "defaultEmailAddress" in dados:
        estado = (dados.get("defaultEmailAddress") or {}).get("marketingState")
        campos["aceita_marketing"] = estado == INSCRITO
    empresa = (dados.get("defaultAddress") or {}).get("company")
    if empresa:
        campos["empresa"] = empresa[:150]
    return campos


def _gasto(dados):
    try:
        # Sem `or None`: Decimal("0.00") e falso e um gasto zero viraria "nao veio".
        return dinheiro(str((dados.get("amountSpent") or {}).get("amount") or ""))
    except ValorInvalido:
        return None


def _inteiro(valor):
    try:
        return int(str(valor))
    except ValueError:
        return None


def comprou_no_shopify(dados):
    # amountSpent primeiro: numberOfOrders conta pedido nao pago (boleto vencido,
    # pagamento pendente). A contagem so decide quando o valor nao veio.
    gasto = _gasto(dados)
    if gasto is not None:
        return gasto > 0
    return (_inteiro(dados.get("numberOfOrders")) or 0) > 0


def _pagante(cliente, dados):
    if comprou_no_shopify(dados):
        return True
    return Pedido.objects.filter(cliente=cliente, status__in=Pedido.PAGOS).exists()


def _so_do_shopify(dados):
    extra = {}
    if dados.get("numberOfOrders") is not None:
        extra["numberOfOrders"] = _inteiro(dados["numberOfOrders"])
    gasto = _gasto(dados)
    if gasto is not None:
        moeda = (dados.get("amountSpent") or {}).get("currencyCode") or ""
        extra["amountSpent"] = {"amount": f"{gasto:.2f}", "currencyCode": moeda}
    if "tags" in dados:
        extra["tags"] = list(dados.get("tags") or [])
    if dados.get("state"):
        extra["state"] = str(dados["state"]).upper()
    try:
        criado = parse_datetime(str(dados.get("createdAt") or ""))
    except ValueError:  # formato certo com data impossivel (mes 13): fica sem data
        criado = None
    if criado:
        # Mesmo instante com fusos diferentes (busca em UTC, webhook em -03:00).
        extra["createdAt"] = (criado.astimezone(UTC) if criado.tzinfo else criado).isoformat()
    return extra, criado


def _vinculo(externo_id):
    return ExternalReference.objects.filter(
        platform=Origin.SHOPIFY, entity_type=ENTIDADE, external_id=externo_id
    ).first()


def _aplicar(cliente_id, dados, sobrescrever, criado):
    with transaction.atomic():
        # Lock e releitura: a API Woo marca cliente_pagante no mesmo cliente, e um
        # save com o retrato velho apagaria esse True.
        cliente = Cliente.objects.select_for_update().get(pk=cliente_id)
        campos = _campos(dados)
        if sobrescrever:
            if _email(dados):
                campos["email"] = _email(dados)
        else:
            campos = {campo: v for campo, v in campos.items() if v and not getattr(cliente, campo)}
        if not cliente.cliente_pagante and _pagante(cliente, dados):
            campos["cliente_pagante"] = True  # so liga: nunca desmarca um True
        mudou = {campo: v for campo, v in campos.items() if getattr(cliente, campo) != v}
        if mudou:
            for campo, valor in mudou.items():
                setattr(cliente, campo, valor)
            cliente.save()
        extra, criado_em = _so_do_shopify(dados)
        if criado and criado_em:
            # Como a API Woo: a data do cadastro e a da loja, nao a da importacao.
            Cliente.objects.filter(pk=cliente.pk).update(created_at=criado_em)
            cliente.created_at = criado_em
        vinculo = _vinculo(dados["id"])
        if vinculo and extra and {**vinculo.metadata, **extra} != vinculo.metadata:
            vinculo.metadata = {**vinculo.metadata, **extra}
            vinculo.save()
        sincronizar_enderecos(cliente, dados)
    return cliente


def importar_cliente(dados):
    externo_id = dados["id"]
    vinculo = _vinculo(externo_id)
    cliente = Cliente.objects.filter(pk=vinculo.object_id).first() if vinculo else None
    criado = False
    if cliente is None:
        sufixo = externo_id.rsplit("/", 1)[-1]
        email = _email(dados) or f"shopify-{sufixo}@sem-email.invalid"
        cliente, criado = Cliente.objects.get_or_create(
            email_normalizado=email.lower().casefold(),
            defaults={"email": email, **_campos(dados), "origin": Origin.SHOPIFY},
        )
        ExternalReference.objects.get_or_create(
            platform=Origin.SHOPIFY, entity_type=ENTIDADE, external_id=externo_id,
            defaults={"object_id": str(cliente.pk), "origin": Origin.SHOPIFY},
        )
    return _aplicar(cliente.pk, dados, sobrescrever=False, criado=criado), criado


def atualizar_cliente(dados):
    """So o cliente ja vinculado; sem vinculo devolve (None, False)."""
    vinculo = _vinculo(dados["id"])
    cliente = Cliente.objects.filter(pk=vinculo.object_id).first() if vinculo else None
    if cliente is None:
        return None, False
    return _aplicar(cliente.pk, dados, sobrescrever=True, criado=False), True
