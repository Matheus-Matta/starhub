"""Shopify como destino do envio: junta os enviadores de cada recurso e se registra."""

from apps.integracoes.envio.base import Marketplace
from apps.integracoes.envio.registro import registrar
from apps.shopify.envio.avaliacoes import AvaliacaoShopify
from apps.shopify.envio.categorias import CategoriaShopify
from apps.shopify.envio.clientes import ClienteShopify
from apps.shopify.envio.cupons import CupomShopify
from apps.shopify.envio.estoque import EstoqueShopify
from apps.shopify.envio.pedidos import PedidoShopify
from apps.shopify.envio.produtos import ProdutoShopify


@registrar
class ShopifyMarketplace(Marketplace):
    plataforma = "shopify"
    recursos = (
        ProdutoShopify, EstoqueShopify, ClienteShopify,
        CategoriaShopify, CupomShopify, PedidoShopify, AvaliacaoShopify,
    )
