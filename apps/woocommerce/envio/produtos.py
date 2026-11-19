"""Produto do hub -> produto do WooCommerce (products), com as variacoes.

Produto variavel: depois do produto, as variacoes vao num lote so
(products/<id>/variations/batch): a ligada ao Woo e atualizada, a nova e criada e
ganha o vinculo "variantes" (com o id do produto pai, que a rota da variacao pede).
Variacao que so existe no Woo fica: o hub nao apaga o que nao criou.

Qual variacao da loja e cada variante: SKU primeiro, depois o vinculo (lista
products/<id>/variations). Vinculo velho (variacao apagada/recriada na loja) dava 404
no lote e o preco alterado nunca chegava; variante sem vinculo com SKU ja na loja era
criada de novo e o Woo recusava ("SKU duplicado").
"""

from apps.core.models import ExternalReference, Origin
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

    def atualizar(self, obj, external_id):
        """Produto apagado na loja (404): acha pelo SKU e religa; senao cria de novo
        (com Enviar > Produtos > Criar ligado). Antes falhava ate alguem reimportar."""
        try:
            return super().atualizar(obj, external_id)
        except WooErro as erro:
            if erro.status != 404:
                raise
            novo = self._produto_pelo_sku(obj)
            ExternalReference.objects.filter(
                platform=Origin.WOOCOMMERCE, entity_type="produtos", object_id=str(obj.pk)
            ).delete()
            if novo:
                vinculos.referenciar("produtos", novo, obj)
                return super().atualizar(obj, novo)
            if not self.configuracao.habilitado("enviar", "produtos", "create"):
                vinculos.referenciar("produtos", external_id, obj)  # fica como estava
                raise WooErro(f"{erro} e nenhum produto da loja tem o SKU dele. Ligue "
                              "Enviar > Produtos > Criar para o hub criar de novo.",
                              erro.status) from erro
            self.vincular(obj, self.criar(obj))
            return None

    def _produto_pelo_sku(self, produto):
        """Id do unico produto da loja com o SKU de alguma variante (pai da variacao)."""
        achados = set()
        for sku in produto.variantes.exclude(sku="").values_list("sku", flat=True):
            for item in self.cliente.get("products", sku=sku.strip()) or []:
                achados.add(str(item.get("parent_id") or item["id"]))
        return achados.pop() if len(achados) == 1 else None

    def depois(self, obj, resposta):
        produtos_imagens.vincular(self._midias, resposta)
        if obj.tipo == Produto.Tipo.VARIAVEL:
            self._variacoes(obj, resposta["id"])

    def _variacoes(self, produto, produto_id):
        criar, atualizar, novas = [], [], []
        variantes = list(produto.variantes.order_by("posicao", "id"))
        ids = self._casar(variantes, produto_id)
        for variante in variantes:
            corpo = corpo_variacao(variante)
            woo_id = ids.get(variante.pk)
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

    def _casar(self, variantes, produto_id):
        """{pk: id da variacao na loja}: SKU primeiro, depois o vinculo. Loja sem
        nenhuma variacao listada (produto novo, ou a lista falhou) fica so com o vinculo."""
        ligados = {v.pk: vinculos.externo_id("variantes", v.pk) for v in variantes}
        try:
            loja = list(self.cliente.listar(f"products/{produto_id}/variations"))
        except WooErro:
            loja = []
        if not loja:
            return {pk: externo for pk, externo in ligados.items() if externo}
        livres = {str(item["id"]): item for item in loja}
        ids = {}
        for variante in variantes:
            sku = (variante.sku or "").strip()
            achada = next((i for i in livres.values()
                           if sku and (i.get("sku") or "").strip() == sku), None)
            if achada:
                ids[variante.pk] = str(livres.pop(str(achada["id"]))["id"])
        for variante in variantes:
            externo = str(ligados.get(variante.pk) or "")
            if variante.pk not in ids and externo in livres:
                ids[variante.pk] = str(livres.pop(externo)["id"])
        for variante in variantes:
            if variante.pk in ids and str(ligados.get(variante.pk) or "") != ids[variante.pk]:
                _religar(variante, ids[variante.pk], produto_id)
        return ids


def _religar(variante, externo, produto_id):
    """Um vinculo por variante: o velho (outro id) sai e o achado pelo SKU entra."""
    ExternalReference.objects.filter(
        platform=Origin.WOOCOMMERCE, entity_type="variantes", object_id=str(variante.pk)
    ).exclude(external_id=str(externo)).delete()
    vinculos.referenciar("variantes", externo, variante, pai=produto_id)
