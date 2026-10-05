"""Pedido do hub -> pedido do WooCommerce: so status e endereco de entrega.

O pedido nasce na loja: criar e excluir nao sao suportados. Itens e valores nao
voltam (mudariam o financeiro do pedido la). Status do hub que o Woo nao tem
(confirmado, arquivado) nao e enviado.
"""

from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.loja.models import Pedido
from apps.loja.services.enderecos import para_woo
from apps.woocommerce.envio.base import RecursoWoo

STATUS_WOO = {"pending", "processing", "on-hold", "completed", "cancelled", "refunded",
              "failed"}


class PedidoWoo(RecursoWoo):
    recurso = entidade = "pedidos"
    modelo = Pedido
    rota = "orders"

    def criar(self, obj):
        raise EnvioNaoSuportado("pedido nasce no WooCommerce: o hub nao cria pedido la.")

    def excluir(self, external_id):
        raise EnvioNaoSuportado("pedido nao e excluido no WooCommerce pelo hub.")

    def corpo(self, obj, criando):
        corpo = {}
        if obj.status in STATUS_WOO:
            corpo["status"] = obj.status
        if obj.endereco_entrega_id:
            corpo["shipping"] = {k: v for k, v in para_woo(obj.endereco_entrega, {}).items()
                                 if k != "email"}
        return corpo
