"""Opcoes da API Woo de pedidos que vem da configuracao FDC Sistemas da conta.

Id do pedido na API = id do hub + base da conta (ex.: 13000: pedido 1 -> 13001). O ERP
legado importa em sequencia pelo id; a base evita que o id do hub, que recomeca do 1,
colida com os pedidos antigos dele. So a borda da API converte: o hub segue com o id dele.
"""

from typing import NamedTuple

from apps.woo_api.models import ConfiguracaoFdc


class Opcoes(NamedTuple):
    base_id: int = 0


def opcoes_da_conta(account_id):
    # Sem filtrar active: desligar a integracao mudaria o id de todos os pedidos para o ERP.
    base = (ConfiguracaoFdc.all_objects.filter(account_id=account_id)
            .values_list("base_id_pedido", flat=True).first())
    return Opcoes(base or 0)


def id_do_hub(id_api, base):
    """Id ate a base e pedido antigo do ERP: vira 0, que nao existe, e nunca o pedido do hub
    de mesmo numero."""
    return id_api - base if id_api > base else 0
