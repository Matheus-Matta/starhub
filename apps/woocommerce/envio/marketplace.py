"""WooCommerce como destino do envio: junta os enviadores de cada recurso e se registra."""

from apps.integracoes.envio.base import Marketplace
from apps.integracoes.envio.registro import registrar
from apps.woocommerce.envio.cadastros import CategoriaWoo, ClienteWoo, CupomWoo
from apps.woocommerce.envio.estoque import EstoqueWoo
from apps.woocommerce.envio.pedidos import PedidoWoo
from apps.woocommerce.envio.produtos import ProdutoWoo


@registrar
class WooCommerceMarketplace(Marketplace):
    plataforma = "woocommerce"
    recursos = (ProdutoWoo, EstoqueWoo, CategoriaWoo, ClienteWoo, CupomWoo, PedidoWoo)

    def habilitado(self, recurso, operacao):
        # Criar pedido na loja e o switch "pedido legado", nao a matriz: a matriz ja
        # tinha Enviar > Pedidos > Criar ligado em lojas onde isso nao fazia nada, e
        # ligar o envio de verdade por ela criaria pedidos sem ninguem pedir.
        if (recurso, operacao) == ("pedidos", "create"):
            return self.configuracao.pedido_legado
        return super().habilitado(recurso, operacao)
