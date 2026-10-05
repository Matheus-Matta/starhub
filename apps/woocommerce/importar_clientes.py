"""Cliente da loja WooCommerce no hub, com os enderecos billing/shipping.

    cliente, criado = importar_cliente({"id": 7, "email": "ana@x.com", "first_name": "Ana",
                                        "billing": {"cpf": "123.456.789-09", ...}})

O endereco do Woo ja e o formato do hub (apps/loja/services/enderecos): os campos dos
plugins brasileiros (cpf, number, neighborhood, persontype) entram como vieram.
Sem vinculo, o mesmo e-mail e o mesmo cliente. CPF ou telefone invalido na loja nao
derruba o cadastro: fica em branco e vira aviso na tarefa.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import Address, Origin
from apps.core.validators import somente_digitos, validar_cpf
from apps.loja.models import Cliente
from apps.loja.services.clientes import gravar_endereco_do_cliente
from apps.loja.services.enderecos import COLUNAS
from apps.loja.validators import normalizar_telefone
from apps.woocommerce import vinculos
from apps.woocommerce.contexto import avisar

ORIGEM = Origin.WOOCOMMERCE


def telefone(*candidatos):
    for candidato in candidatos:
        try:
            numero = normalizar_telefone(candidato or "")
        except ValidationError:
            continue
        if numero:
            return numero
    return ""


def cpf(bruto):
    digitos = somente_digitos(bruto or "")
    try:
        validar_cpf(digitos)
    except ValidationError:
        return ""
    return digitos


def endereco(dados):
    """Endereco do Woo sem vazio e cortado no tamanho da coluna (o Address recusa maior)."""
    saida = {}
    for chave, valor in (dados or {}).items():
        valor = "" if valor is None else str(valor).strip()
        if chave in COLUNAS:
            valor = valor[:Address._meta.get_field(COLUNAS[chave]).max_length]
        if valor:
            saida[chave] = valor
    return saida


def _campos(dados):
    cobranca = dados.get("billing") or {}
    campos = {"nome": (dados.get("first_name") or cobranca.get("first_name") or "")[:150],
              "sobrenome": (dados.get("last_name") or cobranca.get("last_name") or "")[:150],
              "telefone": telefone(cobranca.get("phone"), cobranca.get("cellphone")),
              "empresa": (cobranca.get("company") or "")[:150]}
    documento = cpf(cobranca.get("cpf"))
    if documento:
        campos["cpf"] = documento
    if dados.get("username"):
        campos["usuario"] = dados["username"][:150]
    if dados.get("role"):
        campos["papel"] = dados["role"][:50]
    if isinstance(dados.get("is_paying_customer"), bool):
        campos["cliente_pagante"] = dados["is_paying_customer"]
    return campos


def _avisar_documento(obj, dados):
    bruto = (dados.get("billing") or {}).get("cpf")
    if bruto and not cpf(bruto):
        avisar(f"CPF {bruto} da loja e invalido; o cliente ficou sem CPF.",
               recurso="clientes", id=obj.pk, descricao=obj.email, id_externo=dados.get("id"))


@transaction.atomic
def importar_cliente(dados, sobrescrever=False):
    """Cliente novo recebe tudo; o existente so e completado, salvo `sobrescrever`."""
    externo = dados.get("id") or ""
    email = (dados.get("email") or (dados.get("billing") or {}).get("email") or "").strip()
    obj = vinculos.existente("clientes", Cliente, externo) if externo else None
    if obj is None and email:
        obj = Cliente.objects.filter(email_normalizado=email.casefold()).first()
    if obj is None and not email:
        return None, False
    criado = obj is None
    obj = obj or Cliente(email=email, origin=ORIGEM)
    for campo, valor in _campos(dados).items():
        if criado or sobrescrever or not getattr(obj, campo):
            setattr(obj, campo, valor)
    obj.save()
    _avisar_documento(obj, dados)
    for tipo in ("billing", "shipping"):
        limpo = endereco(dados.get(tipo))
        if limpo:
            gravar_endereco_do_cliente(obj, tipo, limpo)
    vinculos.referenciar("clientes", externo, obj)
    return obj, criado
