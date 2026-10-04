"""Remove o demo de uma conta: so registros com a marca (e os usuarios, perfis e
contas demo pelo prefixo). O que a conta ja tinha fica.

A ordem importa por causa das FKs PROTECT: avaliacao e pedido antes de cliente e endereco,
componente de kit antes da variante, produto antes de categoria, perfil antes do
grupo. Registro demo que passou a ser usado por dado de verdade (ex.: o valor
"Preto" numa variante real) e mantido, em vez de travar a limpeza toda.
"""

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import ProtectedError

from apps.core.models import (
    AccessProfile,
    Account,
    Address,
    ExternalReference,
    PublicationPolicy,
    PublicationState,
    SalesChannel,
    User,
)
from apps.loja.demo import PREFIXO_CONTA, eh_demo, prefixo_usuario
from apps.loja.models import (
    Avaliacao,
    Categoria,
    Cliente,
    Cupom,
    ItemBundle,
    Pedido,
    Produto,
    Tag,
    TipoVariante,
    ValorVariante,
)


def _modelos():
    from apps.woo_api.models import ChaveApi

    # Avaliacao primeiro: PROTECT em produto e cliente (as fotos vao junto, CASCADE).
    return [Avaliacao, Pedido, ItemBundle, Cupom, PublicationState, ExternalReference,
            PublicationPolicy, SalesChannel, Produto, ValorVariante, TipoVariante, Categoria, Tag,
            Cliente, Address, ChaveApi]


def _demo(modelo, conta):
    registros = modelo.all_objects.filter(account=conta).only("pk", "metadados")
    return [registro.pk for registro in registros if eh_demo(registro)]


def existe_demo(conta):
    return bool(_demo(Produto, conta))


def _apagar(registros):
    """Apaga um a um: o que esta protegido por dado de verdade fica. Devolve quantos."""
    total = 0
    for registro in registros:
        try:
            with transaction.atomic():
                registro.delete()
            total += 1
        except ProtectedError:
            pass
    return total


def remover(conta):
    """Apaga o demo da conta; devolve {nome do model: quantos}."""
    removidos = {}
    for modelo in _modelos():
        ids = _demo(modelo, conta)
        removidos[str(modelo._meta.verbose_name_plural)] = _apagar(
            modelo.all_objects.filter(pk__in=ids)
        )
    usuarios = User.objects.filter(account=conta, username__startswith=prefixo_usuario(conta))
    removidos["usuarios"] = _apagar(usuarios)
    perfis = AccessProfile.all_objects.filter(pk__in=_demo(AccessProfile, conta))
    grupos = list(perfis.values_list("group", flat=True))
    removidos["perfis de acesso"] = _apagar(perfis)
    _apagar(Group.objects.filter(pk__in=grupos))
    contas = Account.objects.filter(slug__startswith=PREFIXO_CONTA).exclude(pk=conta.pk)
    # Conta nova nasce com os perfis fixos (perfis_padrao), que a protegem: saem antes.
    AccessProfile.all_objects.filter(account__in=contas, users__isnull=True).delete()
    removidos["contas"] = _apagar(contas)
    return {nome: total for nome, total in removidos.items() if total}
