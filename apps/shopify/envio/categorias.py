"""Categoria do hub -> colecao manual do Shopify (collectionCreate/Update/Delete).

Usa o argumento `collection` (CollectionCreateInput/CollectionUpdateInput): na
2026-07 o `input: CollectionInput` esta deprecado. `products` nunca e enviado: a
doc diz que ele so vale no create, e quem liga produto a colecao e o envio de produto.
A imagem so vai quando o hub tem uma: omitida, o Shopify mantem a atual (mandar
`image: null` apagaria a imagem de colecao cadastrada direto la). E so vai quando a
URL mudou desde o ultimo envio: a cada `image.src` o Shopify baixa a foto de novo.
O registro fica no metadata do vinculo da categoria (apps/shopify/categorias_imagem.py).
"""

from apps.loja.models import Categoria
from apps.shopify import categorias_imagem
from apps.shopify.envio.base import RecursoShopify
from apps.shopify.midias import url_publica

CRIAR = """mutation($colecao: CollectionCreateInput!) {
  collectionCreate(collection: $colecao) { collection { id } userErrors { field message } }
}"""
ATUALIZAR = """mutation($colecao: CollectionUpdateInput!) {
  collectionUpdate(collection: $colecao) { collection { id } userErrors { field message } }
}"""
EXCLUIR = """mutation($input: CollectionDeleteInput!) {
  collectionDelete(input: $input) { deletedCollectionId userErrors { field message } }
}"""


class CategoriaShopify(RecursoShopify):
    recurso = "categorias"
    entidade = "categorias"
    modelo = Categoria

    _imagem_enviada = ""

    def _entrada(self, categoria, registro=None):
        entrada = {"title": categoria.nome, "descriptionHtml": categoria.descricao}
        imagem = categoria.imagem if isinstance(categoria.imagem, dict) else {}
        src = url_publica(self.configuracao, imagem.get("src"))
        self._imagem_enviada = ""
        if src and not categorias_imagem.ja_na_loja(registro, imagem.get("src")):
            entrada["image"] = {"src": src, "altText": imagem.get("alt", "")}
            self._imagem_enviada = imagem["src"]
        return entrada

    def criar(self, obj):
        dados = self.mutacao(CRIAR, {"colecao": self._entrada(obj)}, "collectionCreate")
        return dados["collection"]["id"]

    def vincular(self, obj, external_id):
        super().vincular(obj, external_id)
        self._registrar(obj)

    def atualizar(self, obj, external_id):
        entrada = {"id": self.gid("Collection", external_id),
                   **self._entrada(obj, self._registro(obj))}
        self.mutacao(ATUALIZAR, {"colecao": entrada}, "collectionUpdate")
        self._registrar(obj)

    def _registro(self, obj):
        imagem = obj.imagem if isinstance(obj.imagem, dict) else {}
        # Sem imagem no hub nao ha o que comparar (e o enviador de teste nem tem conta).
        return self._referencias().filter(object_id=str(obj.pk)).first() if imagem else None

    def _registrar(self, obj):
        if self._imagem_enviada:
            categorias_imagem.registrar_envio(self._registro(obj), self._imagem_enviada)

    def excluir(self, external_id):
        self.mutacao(EXCLUIR, {"input": {"id": self.gid("Collection", external_id)}},
                     "collectionDelete")
