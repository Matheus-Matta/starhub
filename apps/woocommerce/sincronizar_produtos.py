"""Produto completo da loja WooCommerce: o produto variavel traz so os ids das
variacoes, e as variacoes vem de GET products/<id>/variations.

    produto = importar_da_loja(configuracao, 15)   # pedido com produto que o hub nao tem
"""

from apps.loja.models import Produto
from apps.woocommerce.cliente import WooClient
from apps.woocommerce.importar_produtos import importar_produto, importar_variacao


def variacoes(cliente, dados):
    if dados.get("type") != Produto.Tipo.VARIAVEL or not dados.get("variations"):
        return []
    return list(cliente.listar(f"products/{dados['id']}/variations"))


def eh_variacao(dados):
    return dados.get("type") == "variation" and bool(dados.get("parent_id"))


def importar_completo(cliente, dados, sobrescrever=False):
    if eh_variacao(dados):
        # Webhook de variacao: o corpo e da variacao, nao do produto. Tratado como
        # produto, o preco e o estoque dela iam para a variante padrao do pai.
        produto = importar_variacao(dados)
        if produto is not None:
            return produto, False
        dados = cliente.get(f"products/{dados['parent_id']}")  # variacao nova: vem no pai
    return importar_produto(dados, variacoes(cliente, dados), sobrescrever=sobrescrever)


def importar_da_loja(configuracao, produto_id):
    cliente = WooClient(configuracao)
    dados = cliente.get(f"products/{produto_id}")
    # Variacao avulsa (o pedido as vezes manda o id da variacao como produto): o pai
    # e quem tem as opcoes e as outras variacoes.
    if dados.get("parent_id"):
        dados = cliente.get(f"products/{dados['parent_id']}")
    return importar_completo(cliente, dados, sobrescrever=True)[0]
