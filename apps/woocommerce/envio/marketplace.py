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
