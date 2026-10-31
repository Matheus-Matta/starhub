"""billing/shipping do Woo. Campos extras (cpf, cnpj, number, neighborhood,
persontype... dos plugins brasileiros) sao guardados e devolvidos como vieram.

As chaves e a ordem seguem o Woo real com o plugin Brazilian Market (o ERP le
campo por campo): o documento e da cobranca, a entrega so tem numero e bairro.
"""

from django.core.exceptions import ValidationError

from apps.loja.services import enderecos
from apps.woo_api.erros import parametro_invalido

CAMPOS_ENDERECO = (
    "first_name", "last_name", "company", "address_1", "address_2",
    "city", "state", "postcode", "country",
)
DA_PESSOA = ("persontype", "cpf", "rg", "cnpj", "ie", "birthdate", "gender", "cellphone")
PADROES = {
    "billing": dict.fromkeys(
        (*CAMPOS_ENDERECO, "email", "phone", "number", "neighborhood", *DA_PESSOA), ""),
    "shipping": dict.fromkeys((*CAMPOS_ENDERECO, "phone", "number", "neighborhood"), ""),
}
# O Shopify e o meta _billing_persontype usam 1/2; o billing do plugin usa F/J.
TIPO_PESSOA = {"1": "F", "2": "J"}


def _pessoa(dados, cliente):
    if cliente is not None:
        dados["cpf"] = dados["cpf"] or cliente.cpf
        dados["cnpj"] = dados["cnpj"] or cliente.cnpj
    tipo = TIPO_PESSOA.get(dados["persontype"], dados["persontype"])
    if not tipo and (dados["cpf"] or dados["cnpj"]):
        tipo = "F" if dados["cpf"] else "J"
    dados["persontype"] = tipo


def saida(endereco, tipo, cliente=None):
    """`cliente`: o cadastro completa o documento que o endereco nao trouxe."""
    dados = enderecos.para_woo(endereco, PADROES[tipo])
    if tipo == "shipping":
        return {chave: valor for chave, valor in dados.items()
                if chave not in DA_PESSOA and chave != "email"}
    _pessoa(dados, cliente)
    return dados


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
