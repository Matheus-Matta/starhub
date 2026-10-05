"""Estoque da variante do hub -> stock_quantity no WooCommerce (valor absoluto).

Variacao: PUT products/<pai>/variations/<id> (o pai vem do vinculo "variantes").
Produto simples: a variante padrao nao tem vinculo proprio; o estoque vai no
produto (PUT products/<id>). Numero absoluto, nao delta: envio perdido ou repetido
se corrige no proximo.
"""

from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.loja.models import VarianteProduto
from apps.woocommerce import vinculos
from apps.woocommerce.envio.base import RecursoWoo


class EstoqueWoo(RecursoWoo):
    recurso = "estoque"
    entidade = "variantes"
    modelo = VarianteProduto

    def referencia(self, pk):
        """"<pai>/variations/<id>" da variacao, ou "<id>" do produto simples."""
        vinculo = self._referencias().filter(object_id=str(pk)).values_list(
            "external_id", "external_parent_id").first()
        if vinculo:
            externo, pai = vinculo
            return f"{pai}/variations/{externo}" if pai else externo
        variante = VarianteProduto.objects.filter(pk=pk).only("produto_id").first()
        return vinculos.externo_id("produtos", variante.produto_id) if variante else None

    def criar(self, obj):
        raise EnvioNaoSuportado(
            "estoque so vai para produto ja vinculado; envie o produto antes.")

    def excluir(self, external_id):
        raise EnvioNaoSuportado("estoque nao se exclui; sai junto com o produto.")

    def atualizar(self, obj, external_id):
        if not obj.manage_inventory:
            raise EnvioNaoSuportado(
                f"variante {obj.pk} esta sem controle de estoque no hub; nada a enviar.")
        self.cliente.put(f"products/{external_id}",
                         {"manage_stock": True, "stock_quantity": obj.inventory_quantity})
