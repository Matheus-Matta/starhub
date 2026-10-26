"""Pedido do hub -> pedido do WooCommerce.

- criar: liga em Enviar > Pedidos > Criar (matriz); o pedido vai inteiro, no formato
  padrao ou, com o switch "pedido no formato legado", no legado (pedidos_legado.py).
- atualizar: so status e endereco de entrega. Itens e valores nao voltam (mudariam o
  financeiro do pedido la). Status do hub que o Woo nao tem nao e enviado.
- excluir: nao suportado.
"""

from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.loja.models import Pedido
from apps.loja.services.enderecos import para_woo
from apps.woocommerce.envio import pedidos_legado
from apps.woocommerce.envio.base import RecursoWoo

STATUS_WOO = pedidos_legado.STATUS_WOO


class PedidoWoo(RecursoWoo):
    recurso = entidade = "pedidos"
    modelo = Pedido
    rota = "orders"

    def criar(self, obj):
        corpo = pedidos_legado.corpo(obj, legado=self.configuracao.pedido_legado)
        return self.cliente.post(self.rota, corpo)["id"]

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
