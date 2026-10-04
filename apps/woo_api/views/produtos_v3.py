"""Produtos e categorias em wc/v3, com observacao das chamadas do ERP."""

import logging

from apps.woo_api.erros import WooErro
from apps.woo_api.recursos.categorias import CategoriaRecurso
from apps.woo_api.recursos.produtos import ProdutoRecurso
from apps.woo_api.views.base import DetalheView, ListaView
from apps.woo_api.views.lote import LoteView

logger = logging.getLogger("django.request")
_CREDENCIAIS = {"consumer_key", "consumer_secret"}
_CAMPOS_UPDATE_PRODUTO = {"regular_price", "sale_price", "stock_quantity"}


def _parametros_visiveis(request):
    """Copia os filtros sem registrar credenciais enviadas pela URL."""
    parametros = {}
    for chave in request.query_params:
        if chave in _CREDENCIAIS:
            continue
        valores = request.query_params.getlist(chave)
        parametros[chave] = valores[0] if len(valores) == 1 else valores
    return parametros


def _produto_somente_update():
    return WooErro(
        "rest_no_route",
        "Produtos da API v3 aceitam somente atualizacao de preco e estoque.",
        404,
    )


class ProdutoV3Recurso(ProdutoRecurso):
    def gravar(self, obj, dados, criando):
        if criando:
            raise _produto_somente_update()
        permitidos = {campo: dados[campo] for campo in _CAMPOS_UPDATE_PRODUTO if campo in dados}
        return super().gravar(obj, permitidos, criando=False)


class ProdutoListaV3View(ListaView):
    recurso_classe = ProdutoV3Recurso

    def get(self, request):
        logger.info("Woo v3 consultou produtos: filtros=%s", _parametros_visiveis(request))
        return super().get(request)

    def post(self, request):
        logger.info("Woo v3 ignorou criacao de produto: corpo=%s", request.data)
        raise _produto_somente_update()


class ProdutoDetalheV3View(DetalheView):
    recurso_classe = ProdutoV3Recurso

    def get(self, request, pk):
        logger.info("Woo v3 consultou o produto %s", pk)
        return super().get(request, pk)

    def put(self, request, pk):
        logger.info("Woo v3 recebeu atualizacao do produto %s: corpo=%s", pk, request.data)
        return super().put(request, pk)

    patch = put
    post = put

    def delete(self, request, pk):
        logger.info("Woo v3 ignorou exclusao do produto %s", pk)
        raise _produto_somente_update()


class ProdutoLoteV3View(LoteView):
    recurso_classe = ProdutoV3Recurso

    def post(self, request):
        logger.info("Woo v3 recebeu lote de produtos: corpo=%s", request.data)
        corpo = self.corpo()
        if corpo.get("create") or corpo.get("delete"):
            raise WooErro(
                "rest_invalid_param",
                "O lote de produtos da API v3 aceita somente update.",
                400,
            )
        return super().post(request)

    put = post
    patch = post


class CategoriaListaV3View(ListaView):
    recurso_classe = CategoriaRecurso

    def get(self, request):
        logger.info("Woo v3 consultou categorias: filtros=%s", _parametros_visiveis(request))
        return super().get(request)

    def post(self, request):
        logger.info("Woo v3 recebeu criacao de categoria: corpo=%s", request.data)
        return super().post(request)


class CategoriaDetalheV3View(DetalheView):
    recurso_classe = CategoriaRecurso

    def get(self, request, pk):
        logger.info("Woo v3 consultou a categoria %s", pk)
        return super().get(request, pk)

    def put(self, request, pk):
        logger.info("Woo v3 recebeu atualizacao da categoria %s: corpo=%s", pk, request.data)
        return super().put(request, pk)

    patch = put
    post = put


class CategoriaLoteV3View(LoteView):
    recurso_classe = CategoriaRecurso

    def post(self, request):
        logger.info("Woo v3 recebeu lote de categorias: corpo=%s", request.data)
        return super().post(request)

    put = post
    patch = post
