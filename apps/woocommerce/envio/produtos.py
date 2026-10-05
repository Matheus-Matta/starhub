"""Produto do hub -> produto do WooCommerce (products), com as variacoes.

Produto variavel: depois do produto, as variacoes vao num lote so
(products/<id>/variations/batch): a ligada ao Woo e atualizada, a nova e criada e
ganha o vinculo "variantes" (com o id do produto pai, que a rota da variacao pede).
Variacao que so existe no Woo fica: o hub nao apaga o que nao criou.
"""

from apps.loja.models import Produto
from apps.woocommerce import vinculos
from apps.woocommerce.cliente import WooErro
from apps.woocommerce.envio import produtos_imagens
from apps.woocommerce.envio.base import RecursoWoo
from apps.woocommerce.envio.produtos_campos import corpo_produto, corpo_variacao


class ProdutoWoo(RecursoWoo):
    recurso = "produtos"
    entidade = "produtos"
    modelo = Produto
    rota = "products"

    _midias = ()

    def corpo(self, obj, criando):
        corpo = corpo_produto(obj)
        corpo["images"], self._midias = produtos_imagens.imagens(self.configuracao, obj)
        return corpo

    def depois(self, obj, resposta):
        produtos_imagens.vincular(self._midias, resposta)
        if obj.tipo == Produto.Tipo.VARIAVEL:
            self._variacoes(obj, resposta["id"])

    def _variacoes(self, produto, produto_id):
        criar, atualizar, novas = [], [], []
        for variante in produto.variantes.order_by("posicao", "id"):
            corpo = corpo_variacao(variante)
            woo_id = vinculos.externo_id("variantes", variante.pk)
            if woo_id:
                atualizar.append({"id": int(woo_id), **corpo})
            else:
                criar.append(corpo)
                novas.append(variante)
        if not criar and not atualizar:
            return
        resposta = self.cliente.post(f"products/{produto_id}/variations/batch",
                                     {"create": criar, "update": atualizar})
        # O lote responde na ordem enviada; item recusado volta com "error" e sem id.
        erros = []
        for variante, criada in zip(novas, resposta.get("create") or [], strict=False):
            if criada.get("id"):
                vinculos.referenciar("variantes", criada["id"], variante, pai=produto_id)
            else:
                erros.append(f"{variante.sku or variante.titulo}: "
                             f"{(criada.get('error') or {}).get('message', 'recusada')}")
        for item in resposta.get("update") or []:
            if item.get("error"):
                erros.append(f"variacao {item.get('id')}: {item['error'].get('message')}")
        if erros:
            raise WooErro("WooCommerce recusou variacoes: " + "; ".join(erros))
