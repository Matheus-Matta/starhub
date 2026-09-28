"""billing/shipping do Woo. Campos extras (cpf, cnpj, number, neighborhood,
persontype... dos plugins brasileiros) sao guardados e devolvidos como vieram."""

from django.core.exceptions import ValidationError

from apps.loja.services import enderecos
from apps.woo_api.erros import parametro_invalido

CAMPOS_ENDERECO = (
    "first_name", "last_name", "company", "address_1", "address_2",
    "city", "state", "postcode", "country",
)
PADROES = {
    "billing": {**dict.fromkeys(CAMPOS_ENDERECO, ""), "email": "", "phone": ""},
    "shipping": {**dict.fromkeys(CAMPOS_ENDERECO, ""), "phone": ""},
}


def saida(endereco, tipo):
    return enderecos.para_woo(endereco, PADROES[tipo])


def recebido(dados, tipo):
    """O objeto enviado em billing/shipping, ou None quando o campo nao veio."""
    valor = dados.get(tipo)
    if valor is None:
        return None
    if not isinstance(valor, dict):
        raise parametro_invalido(tipo, f"{tipo} nao e do tipo object.")
    return valor


def gravar(funcao, *args, tipo):
    """Roda a gravacao do endereco; erro de validacao vira rest_invalid_param do campo."""
    try:
        return funcao(*args)
    except ValidationError as erro:
        raise parametro_invalido(tipo, "; ".join(erro.messages)) from erro
