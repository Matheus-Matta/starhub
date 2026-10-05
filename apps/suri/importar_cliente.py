"""Comprador do pedido do Suri -> Cliente do hub e endereco no formato Woo do hub.

O Suri vende pelo WhatsApp: o comprador pode nao ter e-mail. Sem e-mail o pedido fica
sem Cliente (o Cliente do hub exige e-mail), mas com nome, telefone e endereco no
proprio pedido. CPF ou telefone fora do padrao fica em branco, nao derruba o pedido.
"""

from django.core.exceptions import ValidationError

from apps.core.models import Address, Origin
from apps.core.validators import somente_digitos, validar_cpf
from apps.loja.models import Cliente
from apps.loja.services.clientes import gravar_endereco_do_cliente
from apps.loja.services.enderecos import COLUNAS
from apps.loja.validators import normalizar_telefone


def telefone(bruto):
    try:
        return normalizar_telefone(bruto or "")
    except ValidationError:
        return ""


def cpf(bruto):
    digitos = somente_digitos(bruto or "")
    try:
        validar_cpf(digitos)
    except ValidationError:
        return ""
    return digitos


def _nomes(nome):
    partes = (nome or "").strip().split(None, 1)
    return (partes[0] if partes else ""), (partes[1] if len(partes) > 1 else "")


def endereco(comprador):
    """Endereco do comprador no formato Woo do hub, sem vazio e cortado na coluna."""
    origem = comprador.get("address") or {}
    primeiro, ultimo = _nomes(comprador.get("name"))
    dados = {"first_name": primeiro, "last_name": ultimo, "address_1": origem.get("street"),
             "number": origem.get("number"), "address_2": origem.get("complement"),
             "neighborhood": origem.get("neighborhood"), "city": origem.get("city"),
             "state": origem.get("state"), "postcode": origem.get("zipCode"),
             "country": "BR" if origem else "", "phone": comprador.get("phone"),
             "email": comprador.get("email"), "cpf": cpf(comprador.get("document"))}
    saida = {}
    for chave, valor in dados.items():
        valor = "" if valor is None else str(valor).strip()
        if chave in COLUNAS:
            valor = valor[:Address._meta.get_field(COLUNAS[chave]).max_length]
        if valor:
            saida[chave] = valor
    return saida


def cliente_do_pedido(comprador):
    """Cliente pelo e-mail (cria se faltar); None sem e-mail."""
    email = (comprador.get("email") or "").strip()
    if not email:
        return None
    obj = Cliente.objects.filter(email_normalizado=email.casefold()).first()
    if obj is None:
        primeiro, ultimo = _nomes(comprador.get("name"))
        obj = Cliente(email=email, nome=primeiro[:150], sobrenome=ultimo[:150],
                      telefone=telefone(comprador.get("phone")),
                      cpf=cpf(comprador.get("document")), origin=Origin.SURI)
        obj.save()
        dados = endereco(comprador)
        if dados.get("address_1"):
            gravar_endereco_do_cliente(obj, "billing", dados)
    return obj
