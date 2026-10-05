"""Suri Shop como destino do envio: junta os enviadores de cada recurso e se registra."""

from apps.integracoes.envio.base import Marketplace
from apps.integracoes.envio.registro import registrar
from apps.suri.envio.categorias import CategoriaSuri
from apps.suri.envio.produtos import EstoqueSuri, PedidoSuri, ProdutoSuri


@registrar
class SuriMarketplace(Marketplace):
    plataforma = "suri"
    recursos = (ProdutoSuri, EstoqueSuri, CategoriaSuri, PedidoSuri)
