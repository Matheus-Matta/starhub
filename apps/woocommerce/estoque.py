"""So o estoque: atualiza a quantidade das variantes ja vinculadas, sem mexer no resto.

Recurso "estoque" da sincronizacao: para quem recebe o estoque da loja mas cuida do
catalogo no hub. Produto que o hub nao conhece fica de fora (o recurso e estoque).
"""

from apps.loja.models import Produto, VarianteProduto
from apps.woocommerce import vinculos
from apps.woocommerce.sincronizar_produtos import variacoes


def _aplicar(variante, dados):
    if variante is None or dados.get("stock_quantity") is None:
        return False
    variante.inventory_quantity = int(dados["stock_quantity"])
    if dados.get("stock_status") in VarianteProduto.SituacaoEstoque.values:
        variante.stock_status = dados["stock_status"]
    # save(), nao update(): o Produto recalcula a situacao do estoque no save.
    variante.save()
    return True


def atualizar_estoque(cliente, dados):
    """(variante ou produto atualizado, False): o estoque nunca cria cadastro."""
    produto = vinculos.existente("produtos", Produto, dados.get("id"))
    if produto is None:
        return None, False
    if dados.get("type") == Produto.Tipo.VARIAVEL:
        for variacao in variacoes(cliente, dados):
            _aplicar(vinculos.existente("variantes", VarianteProduto, variacao["id"]), variacao)
    else:
        _aplicar(produto.variante_padrao, dados)
    return produto, False
