"""`name` do ERP na v3: vai para o produto ou para a variante que o SKU (ou o id) acha.

- Variante de produto com mais de uma variante: vira o TITULO dela. O nome da variacao na API e
  "<nome do produto> - <titulo>" (produtos_variacao.py), entao o ERP costuma mandar o
  nome inteiro: o comeco igual ao nome do produto sai e fica so o resto ("SOFA X -
  Veludo Azul" -> "Veludo Azul"). Sobrou nada (ex.: "SOFA X-")? O titulo nao muda.
- Produto de uma variante so, ou PUT pelo id do produto: vira o nome do produto. (Conta
  quantas variantes o produto tem, nao o tipo: produto do Shopify marcado como simples
  pode ter varias, e o nome de uma delas renomearia o produto inteiro.)

Nome vazio nunca apaga nada.
"""

from apps.loja.models import Produto
from apps.woo_api.recursos.base import texto

SEPARADORES = " -|/–—:"


def nome_de(dados):
    return " ".join(texto(dados.get("name") or "", "name", 255).split())


def titulo_da_variacao(nome_produto, nome):
    """O que sobra do `name` depois do nome do produto; o nome todo se nao comeca com ele."""
    base = " ".join((nome_produto or "").split())
    if base and nome.casefold().startswith(base.casefold()):
        return nome[len(base):].strip(SEPARADORES)
    return nome


def e_do_produto(variante):
    return not variante.produto.variantes.exclude(pk=variante.pk).exists()


def renomear_produto(produto_id, nome):
    produto = Produto.objects.get(pk=produto_id)
    if produto.nome != nome:
        produto.nome = nome
        produto.save()  # save() completo: o envio as lojas compara antes x depois


def aplicar_na_variante(variante, nome):
    """Grava o `name` no produto (simples) ou poe o titulo na variante (salva depois)."""
    if not nome:
        return
    if e_do_produto(variante):
        renomear_produto(variante.produto_id, nome)
        return
    titulo = titulo_da_variacao(variante.produto.nome, nome)
    if titulo:
        variante.titulo = titulo[:255]
