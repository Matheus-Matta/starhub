"""Produto do hub -> Product do Shopify.

- criar: productSet, o produto inteiro (dados, opcoes e variantes) numa chamada so.
- atualizar: productUpdate (so os campos do produto) + variantes em lote. NUNCA
  productSet: nele toda lista omitida ou incompleta (colecoes, midias, metafields,
  variantes) e apagada na loja, e cada edicao no hub arrancaria imagens e colecoes.
  Variante que so existe no Shopify fica; variante nova do hub e criada.
- excluir: productDelete.
- imagens: ver produtos_midias.py (create manda `files`; update acrescenta `media`).
"""

from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.loja.models import Produto
from apps.shopify.envio import produtos_midias as midias_shopify
from apps.shopify.envio import produtos_variantes as variantes_shopify
from apps.shopify.envio.base import RecursoShopify

CRIAR = """mutation($input: ProductSetInput!) {
  productSet(input: $input, synchronous: true) {
    product { id media(first: 250) { nodes { id } }
      variants(first: 250) { nodes { id position inventoryItem { id } } } }
    userErrors { field message code }
  }
}"""
ATUALIZAR = """mutation($product: ProductUpdateInput!, $media: [CreateMediaInput!]) {
  productUpdate(product: $product, media: $media) {
    product { id media(last: 250) { nodes { id } } } userErrors { field message }
  }
}"""
ATUALIZAR_VARIANTES = """mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants { id } userErrors { field message }
  }
}"""
CRIAR_VARIANTES = """mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!,
    $strategy: ProductVariantsBulkCreateStrategy) {
  productVariantsBulkCreate(productId: $productId, variants: $variants, strategy: $strategy) {
    productVariants { id inventoryItem { id } } userErrors { field message }
  }
}"""
EXCLUIR = """mutation($input: ProductDeleteInput!) {
  productDelete(input: $input, synchronous: true) { deletedProductId userErrors { field message } }
}"""

STATUS = {
    Produto.Status.PUBLICADO: "ACTIVE",
    Produto.Status.ARQUIVADO: "ARCHIVED",
    Produto.Status.LIXEIRA: "ARCHIVED",
}


class ProdutoShopify(RecursoShopify):
    recurso = "produtos"
    entidade = "produtos"
    modelo = Produto

    def criar(self, obj):
        variantes = self._variantes(obj)
        imagens = midias_shopify.pendentes(self, obj)
        pares = [variantes_shopify.opcoes_da_variante(v, len(variantes) > 1) for v in variantes]
        entrada = {
            **self._campos(obj),
            "productOptions": variantes_shopify.opcoes_do_produto(pares),
            "variants": [
                self._nova_no_set(v, posicao, opcoes)
                for posicao, (v, opcoes) in enumerate(zip(variantes, pares, strict=True), 1)
            ],
        }
        if imagens:
            entrada["files"] = midias_shopify.arquivos(imagens)
        produto = self.mutacao(CRIAR, {"input": entrada}, "productSet")["product"]
        midias_shopify.registrar(self, imagens, _midias(produto), produto["id"])
        por_posicao = {n.get("position"): n for n in produto["variants"]["nodes"]}
        for posicao, variante in enumerate(variantes, 1):
            if posicao in por_posicao:
                variantes_shopify.vincular(self, variante, por_posicao[posicao], produto["id"])
        return produto["id"]

    def atualizar(self, obj, external_id):
        produto_gid = self.gid("Product", external_id)
        variantes = self._variantes(obj)
        imagens = midias_shopify.pendentes(self, obj)
        variaveis = {"product": {"id": produto_gid, **self._campos(obj)}}
        if imagens:
            variaveis["media"] = midias_shopify.novas(imagens)
        produto = self.mutacao(ATUALIZAR, variaveis, "productUpdate").get("product") or {}
        # As novas entram no fim da lista de midias do produto, na ordem enviada.
        recebidas = _midias(produto)[-len(imagens):] if imagens else []
        midias_shopify.registrar(self, imagens, recebidas, produto_gid)
        vinculos = dict(self.referencias_variantes().filter(
            object_id__in=[str(v.pk) for v in variantes]
        ).values_list("object_id", "external_id"))
        vinculadas = [v for v in variantes if str(v.pk) in vinculos]
        novas = [v for v in variantes if str(v.pk) not in vinculos]
        if vinculadas:
            self.mutacao(ATUALIZAR_VARIANTES, {"productId": produto_gid, "variants": [
                {"id": vinculos[str(v.pk)], **variantes_shopify.em_lote(v)} for v in vinculadas
            ]}, "productVariantsBulkUpdate")
        if novas:
            self._criar_variantes(produto_gid, novas, len(variantes) > 1)

    def excluir(self, external_id):
        self.mutacao(EXCLUIR, {"input": {"id": self.gid("Product", external_id)}},
                     "productDelete")

    def _variantes(self, produto):
        variantes = list(produto.variantes.all())
        if not variantes:
            raise EnvioNaoSuportado(
                f"produto {produto.pk} ({produto.get_tipo_display()}) nao tem variante; "
                "o Shopify exige ao menos uma."
            )
        return variantes

    def _campos(self, produto):
        campos = {
            "title": produto.nome,
            "descriptionHtml": produto.descricao or "",
            "vendor": produto.fornecedor or produto.marca or "",
            "status": STATUS.get(produto.status, "DRAFT"),
            "tags": [tag.nome for tag in produto.tags.all()],
        }
        # So o que o hub tem: `seo` com texto vazio apagaria o SEO cadastrado na loja.
        seo = {chave: valor for chave, valor in (
            ("title", produto.seo_titulo), ("description", produto.seo_descricao)) if valor}
        if seo:
            campos["seo"] = seo
        return campos

    def _estoque_inicial(self, variante, formato):
        # So na criacao da variante: depois o estoque segue pelo recurso "estoque",
        # que tem o seu proprio liga/desliga na configuracao.
        if not variante.manage_inventory:
            return None
        if formato == "set":
            return [{"locationId": self.local_principal(), "name": "available",
                     "quantity": variante.inventory_quantity}]
        return [{"locationId": self.local_principal(),
                 "availableQuantity": variante.inventory_quantity}]

    def _nova_no_set(self, variante, posicao, opcoes):
        # ProductVariantSetInput tem `sku` no topo (o lote nao tem).
        dados = {**variantes_shopify.comum(variante), "position": posicao, "sku": variante.sku,
                 "optionValues": variantes_shopify.valores_de_opcao(opcoes)}
        estoque = self._estoque_inicial(variante, "set")
        if estoque:
            dados["inventoryQuantities"] = estoque
        return dados

    def _criar_variantes(self, produto_gid, novas, varias):
        entrada = []
        for variante in novas:
            opcoes = variantes_shopify.opcoes_da_variante(variante, varias)
            dados = {**variantes_shopify.em_lote(variante),
                     "optionValues": variantes_shopify.valores_de_opcao(opcoes)}
            estoque = self._estoque_inicial(variante, "lote")
            if estoque:
                dados["inventoryQuantities"] = estoque
            entrada.append(dados)
        # PRESERVE: o DEFAULT apaga a variante "Default Title" da loja, e o update nunca
        # apaga variante.
        criadas = self.mutacao(CRIAR_VARIANTES, {
            "productId": produto_gid, "variants": entrada,
            "strategy": "PRESERVE_STANDALONE_VARIANT",
        }, "productVariantsBulkCreate").get("productVariants") or []
        # O Shopify devolve as criadas na ordem da entrada.
        for variante, recebida in zip(novas, criadas, strict=False):
            variantes_shopify.vincular(self, variante, recebida, produto_gid)


def _midias(produto):
    return ((produto or {}).get("media") or {}).get("nodes") or []
