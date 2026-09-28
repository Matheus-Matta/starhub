from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.woo_api.recursos.categorias import CategoriaRecurso
from apps.woo_api.recursos.clientes import ClienteRecurso
from apps.woo_api.recursos.pedidos import PedidoRecurso
from apps.woo_api.recursos.produtos import ProdutoRecurso
from apps.woo_api.views.base import DetalheView, ListaView
from apps.woo_api.views.lote import LoteView

RECURSOS = {
    "products": ProdutoRecurso,
    "products/categories": CategoriaRecurso,
    "customers": ClienteRecurso,
    "orders": PedidoRecurso,
}


def views_de(recurso):
    """(lista, detalhe, lote) ligadas ao recurso."""
    return (
        ListaView.as_view(recurso_classe=recurso),
        DetalheView.as_view(recurso_classe=recurso),
        LoteView.as_view(recurso_classe=recurso),
    )


class IndiceView(APIView):
    """GET /wp-json/wc/v1: publico, como no WordPress. ERPs usam para testar a URL."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        base = request.build_absolute_uri("/wp-json/wc/v1/")
        rotas = {}
        for caminho in RECURSOS:
            rotas[f"/wc/v1/{caminho}"] = {"methods": ["GET", "POST"]}
            rotas[f"/wc/v1/{caminho}/(?P<id>[\\d]+)"] = {
                "methods": ["GET", "POST", "PUT", "PATCH", "DELETE"]
            }
            rotas[f"/wc/v1/{caminho}/batch"] = {"methods": ["POST", "PUT", "PATCH"]}
        return Response({"namespace": "wc/v1", "url": base, "routes": rotas})


class RaizView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            "name": "StarHub",
            "description": "Hub de integracao com marketplaces (API compativel com WooCommerce)",
            "url": request.build_absolute_uri("/"),
            "namespaces": ["wc/v1", "jwt-auth/v1"],
        })
