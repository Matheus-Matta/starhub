"""Rotas de variacao do Woo: /wc/v3/products/<pai>/variations[/<id>|/batch].

Com o id proprio da variacao (produtos_variacao.py), o ERP passou a fazer como no Woo:
PUT products/461/variations/1000000856. Sem a rota o hub respondia 404 em HTML e a
variacao nao mudava. Aceita o id da API (1000000000 + variante), o id da variante e o id
do pai (= a variante padrao), sempre dentro do produto da URL. Mesma regra do produto
na v3: so preco, promocao e estoque mudam.
"""

import logging

from rest_framework.response import Response

from apps.loja.models import VarianteProduto
from apps.woo_api.erros import WooErro, id_invalido
from apps.woo_api.paginacao import paginar
from apps.woo_api.recursos.produtos_variacao import BASE_VARIACAO, id_woo, variacao_para_woo
from apps.woo_api.views.base import DetalheView, ListaView
from apps.woo_api.views.lote import LoteView
from apps.woo_api.views.produtos_v3 import ProdutoV3Recurso

logger = logging.getLogger("django.request")
NOME = "product_variation"


def id_da_variacao(pai, id_):
    """Id da URL ou do lote -> o id que o recurso de produto entende (id_woo)."""
    try:
        pai, numero = int(pai), int(id_)
    except (TypeError, ValueError) as erro:
        raise id_invalido(NOME) from erro
    variantes = VarianteProduto.objects.filter(produto_id=pai)
    variante = variantes.filter(
        pk=numero - BASE_VARIACAO if numero > BASE_VARIACAO else numero).first()
    if variante is None and numero == pai:
        variante = variantes.filter(is_default=True).first()
    if variante is None:
        raise id_invalido(NOME)
    return id_woo(variante)


class VariacaoListaV3View(ListaView):
    recurso_classe = ProdutoV3Recurso

    def get(self, request, pai):
        produto = self.recurso().obter(pai)
        variantes = produto.variantes.order_by("posicao", "pk")
        itens, cabecalhos = paginar(request, variantes)
        return Response([variacao_para_woo(produto, v, request) for v in itens],
                        headers=cabecalhos)

    def post(self, request, pai):
        raise WooErro("rest_no_route", "Variacao nao e criada pela API; crie no hub.", 404)


class VariacaoDetalheV3View(DetalheView):
    recurso_classe = ProdutoV3Recurso

    def get(self, request, pai, pk):
        return super().get(request, id_da_variacao(pai, pk))

    def put(self, request, pai, pk):
        logger.info("Woo v3 recebeu atualizacao da variacao %s do produto %s: corpo=%s",
                    pk, pai, request.data)
        return super().put(request, id_da_variacao(pai, pk))

    patch = put
    post = put

    def delete(self, request, pai, pk):
        raise WooErro("woocommerce_rest_cannot_delete",
                      "A variacao nao e excluida pela API; exclua no admin do hub.", 400)


class VariacaoLoteV3View(LoteView):
    recurso_classe = ProdutoV3Recurso

    def post(self, request, pai):
        corpo = self.corpo()
        if corpo.get("create") or corpo.get("delete"):
            raise WooErro("rest_invalid_param",
                          "O lote de variacoes aceita somente update.", 400)
        for item in corpo.get("update") or []:
            if isinstance(item, dict):
                try:
                    item["id"] = id_da_variacao(pai, item.get("id"))
                except WooErro:
                    item["id"] = 0  # o lote devolve o erro do item; os outros seguem
        return super().post(request)

    put = post
    patch = post
