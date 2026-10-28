"""Servico do hub -> produto escondido da Shopify, que o tema poe no carrinho.

A Shopify so cobra o que e item do carrinho: o servico vira um produto com a tag
`starhub-servico`, sem frete, sem estoque e fora da busca (metafield seo.hidden), e
uma variante por preco (o padrao do servico e o de cada regra ativa):

    Montagem (SERV-MONTAGEM): "R$ 80,00" e "R$ 120,00"

O bloco do tema (servicos_publico.py) escolhe a variante do preco que vale para o
produto da pagina. Vinculos: "servicos" (produto) e "servicos_variantes" (variante,
com o preco no metadata). O produto e todo do hub, entao o update usa productSet.
"""

from decimal import Decimal

from apps.core.models import ExternalReference
from apps.core.ui.formatos import moeda
from apps.loja.models import RegraServico, Servico
from apps.shopify.cliente import ShopifyErro
from apps.shopify.envio.base import RecursoShopify
from apps.shopify.envio.produtos_variantes import dinheiro

TAG = "starhub-servico"
OPCAO = "Preco"
VARIANTES = "servicos_variantes"

SALVAR = """mutation($input: ProductSetInput!, $identifier: ProductSetIdentifiers) {
  productSet(input: $input, identifier: $identifier, synchronous: true) {
    product { id variants(first: 250) { nodes { id price } } }
    userErrors { field message code }
  }
}"""
PUBLICACOES = "query { publications(first: 50) { nodes { id name } } }"
PUBLICAR = """mutation($id: ID!, $input: [PublicationInput!]!) {
  publishablePublish(id: $id, input: $input) { userErrors { field message } }
}"""
EXCLUIR = """mutation($input: ProductDeleteInput!) {
  productDelete(input: $input, synchronous: true) { deletedProductId userErrors { field message } }
}"""
LOJA_VIRTUAL = ("online store", "loja virtual")


def precos(servico):
    """Precos distintos do servico, do menor ao maior: o padrao e os das regras ativas."""
    das_regras = RegraServico.objects.filter(
        servico=servico, active=True, preco__isnull=False).values_list("preco", flat=True)
    return sorted({servico.preco, *das_regras})


class ServicoShopify(RecursoShopify):
    recurso = entidade = "servicos"
    modelo = Servico

    def criar(self, obj):
        produto = self._salvar(obj, None)
        self._publicar(produto["id"])
        return produto["id"]

    def atualizar(self, obj, external_id):
        self._salvar(obj, external_id)

    def excluir(self, external_id):
        self.mutacao(EXCLUIR, {"input": {"id": external_id}}, "productDelete")
        self._variantes().filter(external_parent_id=external_id).delete()

    def _variantes(self):
        return ExternalReference.all_objects.filter(
            account_id=self.configuracao.account_id, platform=self.plataforma,
            entity_type=VARIANTES)

    def _entrada(self, servico, external_id):
        lista = precos(servico)
        ja = {} if external_id is None else {
            (ref.metadata or {}).get("preco"): ref.external_id
            for ref in self._variantes().filter(external_parent_id=external_id)}
        variantes = []
        for preco in lista:
            variante = {
                "optionValues": [{"optionName": OPCAO, "name": moeda(preco)}],
                "price": dinheiro(preco), "sku": servico.sku, "taxable": False,
                "inventoryPolicy": "CONTINUE",
                "inventoryItem": {"tracked": False, "requiresShipping": False},
            }
            if ja.get(dinheiro(preco)):
                variante["id"] = ja[dinheiro(preco)]
            variantes.append(variante)
        return {
            "title": servico.nome, "productType": "Servico", "tags": [TAG],
            # Ignorado na Shopify: rascunho, para o carrinho nao aceitar a variante antiga.
            "status": ("ACTIVE" if servico.active and not servico.ignorado_em("shopify")
                       else "DRAFT"),
            "productOptions": [{"name": OPCAO,
                                "values": [{"name": moeda(p)} for p in lista]}],
            "variants": variantes,
            # Fora da busca e dos mapas do site: so o bloco do tema oferece o servico.
            "metafields": [{"namespace": "seo", "key": "hidden", "type": "number_integer",
                            "value": "1"}],
        }

    def _salvar(self, servico, external_id):
        variaveis = {"input": self._entrada(servico, external_id)}
        if external_id:
            variaveis["identifier"] = {"id": external_id}
        produto = self.mutacao(SALVAR, variaveis, "productSet")["product"]
        recebidas = produto["variants"]["nodes"]
        self._variantes().filter(external_parent_id=produto["id"]).exclude(
            external_id__in=[v["id"] for v in recebidas]).delete()
        for variante in recebidas:
            self._variantes().update_or_create(
                account_id=self.configuracao.account_id, platform=self.plataforma,
                entity_type=VARIANTES, external_id=variante["id"],
                defaults={"object_id": str(servico.pk), "external_parent_id": produto["id"],
                          "metadata": {"preco": dinheiro(Decimal(str(variante["price"])))},
                          "origin": self.plataforma})
        return produto

    def _publicar(self, produto_gid):
        # Sem publicar na loja virtual o /cart/add.js do tema recusa a variante.
        nodes = ((self.cliente.graphql(PUBLICACOES) or {}).get("publications") or {}).get(
            "nodes") or []
        loja = next((n["id"] for n in nodes
                     if str(n.get("name") or "").casefold() in LOJA_VIRTUAL), None)
        if loja is None:
            raise ShopifyErro(
                "Nao achei o canal Loja virtual (Online Store) na Shopify: confira o escopo "
                "read_publications/write_publications do app e publique o servico a mao.")
        self.mutacao(PUBLICAR, {"id": produto_gid, "input": [{"publicationId": loja}]},
                     "publishablePublish")
