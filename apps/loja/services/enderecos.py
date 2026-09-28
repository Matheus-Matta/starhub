"""Endereco no formato do WooCommerce (billing/shipping) <-> core.Address.

O que o Address conhece vira coluna; o resto (first_name, cpf, cnpj, persontype
dos plugins brasileiros...) fica em Address.metadata e volta igual para o ERP.

    aplicar(Address(), {"city": "Recife", "cpf": "123.456.789-09"})
    -> city="Recife", document="12345678909", metadata={"cpf": "123.456.789-09"}
"""

from django.core.exceptions import ValidationError

from apps.core.models import Address
from apps.loja.validators import somente_digitos

# chave do Woo -> campo do Address
COLUNAS = {
    "company": "company", "address_1": "address_line_1", "address_2": "address_line_2",
    "number": "number", "neighborhood": "neighborhood", "city": "city",
    "state": "state_code", "postcode": "postal_code", "country": "country_code",
    "email": "email", "phone": "phone",
}
# A coluna guarda normalizado (CEP so com digitos); o ERP recebe de volta como mandou.
COMO_VEIO = {"postcode"}


def aplicar(endereco, dados, substituir=False):
    """Mescla `dados` no endereco (novo ou existente) sem salvar.

    API Woo: chave ausente fica como esta (PUT parcial). Admin (substituir=True):
    o formulario manda o endereco inteiro, entao o que sumiu da tela e apagado.
    """
    metadata = {} if substituir else dict(endereco.metadata or {})
    if substituir:
        for campo in (*COLUNAS.values(), "document"):
            setattr(endereco, campo, "")
    for chave, valor in dados.items():
        valor = "" if valor is None else str(valor)
        if chave not in COLUNAS:
            metadata[chave] = valor
            continue
        campo = COLUNAS[chave]
        tamanho = Address._meta.get_field(campo).max_length
        if len(valor) > tamanho:
            # O Postgres recusaria na gravacao com erro 500; aqui vira erro do campo.
            raise ValidationError({chave: f"{chave} passa de {tamanho} caracteres."})
        setattr(endereco, campo, valor)
        if chave in COMO_VEIO:
            metadata[chave] = valor
    endereco.metadata = metadata
    nomes = (metadata.get("first_name"), metadata.get("last_name"))
    endereco.recipient_name = " ".join(filter(None, nomes))
    documento = metadata.get("cpf") or metadata.get("cnpj")
    if documento is not None:
        endereco.document = somente_digitos(documento)
    return endereco


def para_woo(endereco, padrao):
    """Dict do Woo: as chaves de `padrao` sempre aparecem; coluna extra (number,
    neighborhood) so quando preenchida; o que o ERP mandou a mais volta igual, ate vazio."""
    if endereco is None:
        return dict(padrao)
    dados = dict(padrao)
    for chave, campo in COLUNAS.items():
        valor = getattr(endereco, campo)
        if chave in padrao or valor:
            dados[chave] = valor
    dados.update(endereco.metadata or {})
    return dados


def snapshot(dados, nome, conta=None):
    """Endereco novo, so do pedido: mudar o cadastro do cliente depois nao o altera.

    `conta`: a do pedido. Sem ela vale a conta ativa, que no admin do superusuario
    e a DELE, nao necessariamente a do pedido.
    """
    endereco = aplicar(Address(name=nome, account_id=conta), dados or {})
    endereco.save()
    return endereco


def clonar(endereco, nome):
    """Copia um endereco do cliente para o pedido (o pedido e documento historico)."""
    if endereco is None:
        return None
    copia = Address.objects.get(pk=endereco.pk)
    copia.pk = copia.id = None
    copia._state.adding = True
    copia.name, copia.is_default = nome, False
    copia.save()
    return copia
