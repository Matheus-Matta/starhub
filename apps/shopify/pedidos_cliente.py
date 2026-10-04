"""Cliente do pedido Shopify: vinculado pelo id do Shopify, pelo e-mail ou criado."""

from django.core.exceptions import ValidationError

from apps.core.models import Origin
from apps.loja.models import Cliente
from apps.loja.validators import normalizar_telefone
from apps.shopify import recursos
from apps.shopify.pedidos_base import gid


def _telefone(*candidatos):
    """Telefone fora do padrao nao pode derrubar o pedido inteiro: fica em branco."""
    for candidato in candidatos:
        try:
            telefone = normalizar_telefone(candidato or "")
        except ValidationError:
            continue
        if telefone:
            return telefone
    return ""


def cliente_do_pedido(dados):
    cliente = dados.get("customer") or {}
    cobranca = dados.get("billing_address") or {}
    email = cliente.get("email") or dados.get("email") or dados.get("contact_email") or ""
    telefone = _telefone(cliente.get("phone"), dados.get("phone"), cobranca.get("phone"))
    nome = cliente.get("first_name") or cobranca.get("first_name") or ""
    sobrenome = cliente.get("last_name") or cobranca.get("last_name") or ""
    externo = gid("Customer", cliente.get("admin_graphql_api_id") or cliente.get("id"))
    if externo:
        obj, _criado = recursos.cliente({
            "id": externo, "email": email, "firstName": nome, "lastName": sobrenome,
            "phone": telefone,
        })
        return obj
    if not email:
        return None
    obj, _criado = Cliente.objects.get_or_create(email_normalizado=email.strip().casefold(),
        defaults={"email": email, "nome": nome, "sobrenome": sobrenome,
                  "telefone": telefone, "origin": Origin.SHOPIFY})
    return obj
