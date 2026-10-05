"""Pedidos da API Woo (v3 e v1): so leitura e atualizacao.

Pedido so nasce vindo de marketplace (ex.: Shopify). O ERP le e atualiza, nunca cria
nem apaga; as mesmas views atendem wc/v1/orders e wc/v3/orders. Com o modo "encaminhar
pedidos" ligado na loja WooCommerce, a requisicao vai para a loja (views/encaminhar.py).
"""

import logging

from apps.woo_api.erros import WooErro
from apps.woo_api.recursos.pedidos import PedidoRecurso
from apps.woo_api.views.base import DetalheView, ListaView
from apps.woo_api.views.encaminhar import EncaminharPedidoMixin
from apps.woo_api.views.lote import LoteView
from apps.woo_api.views.produtos_v3 import _parametros_visiveis

logger = logging.getLogger("django.request")


def _pedido_somente_update():
    return WooErro(
        "rest_no_route",
        "Pedidos da API Woo aceitam somente leitura e atualizacao. "
        "Pedido novo chega pelo marketplace (ex.: Shopify), nao por esta API.",
        404,
    )


class PedidoV3Recurso(PedidoRecurso):
    def gravar(self, obj, dados, criando):
        if criando:
            raise _pedido_somente_update()
        return super().gravar(obj, dados, criando=False)

    def excluir(self, obj, forcar):
        raise _pedido_somente_update()


class PedidoListaV3View(EncaminharPedidoMixin, ListaView):
    recurso_classe = PedidoV3Recurso

    def get(self, request):
        logger.info("Woo consultou pedidos: filtros=%s", _parametros_visiveis(request))
        return super().get(request)

    def post(self, request):
        logger.info("Woo recusou criacao de pedido: corpo=%s", request.data)
        raise _pedido_somente_update()


class PedidoDetalheV3View(EncaminharPedidoMixin, DetalheView):
    recurso_classe = PedidoV3Recurso

    def get(self, request, pk):
        logger.info("Woo consultou o pedido %s", pk)
        return super().get(request, pk)

    def put(self, request, pk):
        logger.info("Woo recebeu atualizacao do pedido %s: corpo=%s", pk, request.data)
        return super().put(request, pk)

    patch = put
    post = put

    def delete(self, request, pk):
        logger.info("Woo recusou exclusao do pedido %s", pk)
        raise _pedido_somente_update()


class PedidoLoteV3View(EncaminharPedidoMixin, LoteView):
    recurso_classe = PedidoV3Recurso

    def post(self, request):
        logger.info("Woo recebeu lote de pedidos: corpo=%s", request.data)
        corpo = self.corpo()
        if corpo.get("create") or corpo.get("delete"):
            raise _pedido_somente_update()
        return super().post(request)

    put = post
    patch = post
