"""Id do pedido na API Woo = id do hub + base da conta (ex.: 13000: pedido 1 -> 13001).

O ERP legado importa em sequencia pelo id; a base evita que o id do hub, que recomeca do
1, colida com os pedidos antigos dele. So a borda da API converte: o hub segue com o id dele.
"""

from apps.integracoes.models import ConfiguracaoIntegracao


def base_da_conta(account_id):
    # Sem filtrar active: desligar a integracao mudaria o id de todos os pedidos para o ERP.
    return (ConfiguracaoIntegracao.all_objects
            .filter(account_id=account_id, plataforma=ConfiguracaoIntegracao.Plataforma.WOOCOMMERCE)
            .values_list("base_id_pedido", flat=True).first()) or 0


def id_do_hub(id_api, base):
    """Id ate a base e pedido antigo do ERP: vira 0, que nao existe, e nunca o pedido do hub
    de mesmo numero."""
    return id_api - base if id_api > base else 0
