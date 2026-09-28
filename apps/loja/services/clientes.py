"""Enderecos de cobranca/entrega do cliente, guardados como core.Address.

O cliente pode ter varios enderecos (ClienteEndereco); o padrao de cada tipo e o
que a API Woo devolve em billing/shipping.
"""

from apps.core.models import Address
from apps.loja.models import ClienteEndereco
from apps.loja.services import enderecos


def endereco_do_cliente(cliente, tipo):
    """Endereco padrao do tipo. Le do prefetch de `vinculos_endereco` quando existir."""
    if cliente.pk is None:
        return None
    vinculos = [v for v in cliente.vinculos_endereco.all() if v.tipo == tipo]
    vinculos.sort(key=lambda v: (not v.padrao, v.pk))
    return vinculos[0].endereco if vinculos else None


def gravar_endereco_do_cliente(cliente, tipo, dados, substituir=False):
    """Mescla `dados` (formato Woo) no endereco padrao do tipo, criando se faltar."""
    endereco = endereco_do_cliente(cliente, tipo)
    novo = endereco is None
    endereco = enderecos.aplicar(
        endereco or Address(name=ClienteEndereco.Tipo(tipo).label, account_id=cliente.account_id),
        dados,
        substituir,
    )
    endereco.save()
    if novo:
        ClienteEndereco.objects.create(cliente=cliente, endereco=endereco, tipo=tipo, padrao=True)
    # O prefetch ficou velho: a proxima leitura busca de novo.
    getattr(cliente, "_prefetched_objects_cache", {}).pop("vinculos_endereco", None)
    return endereco
