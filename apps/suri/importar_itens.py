"""Itens do pedido do Suri: um ItemPedido por item, ligado a variante do catalogo.

O item do Suri nao tem id proprio: a chave do vinculo "itens_pedido" e
"<pedido>:<posicao>:<sku>". O produto que o hub nao conhece e buscado no Suri
(GET shop/products/<providerId>) e importado inteiro, nunca um cadastro minimo.
Quantidade fracionada (venda por quilo) nao cabe no hub (inteiro): vira aviso.
"""

from decimal import Decimal

from apps.loja.dinheiro import ZERO, dinheiro
from apps.loja.models import ItemPedido, Produto, VarianteProduto
from apps.loja.totais import valores_do_item
from apps.suri import vinculos
from apps.suri.contexto import avisar, configuracao_atual
from apps.suri.importar_catalogo import valor

ENTIDADE = "itens_pedido"


def _buscar_no_suri(produto_id):
    from apps.suri.cliente import SuriClient
    from apps.suri.importar_catalogo import importar_produto

    configuracao = configuracao_atual()
    if configuracao is None:
        return
    # Erro do Suri sobe de proposito: o pedido inteiro volta e a tarefa fica para retomar.
    importar_produto(SuriClient(configuracao).get(f"shop/products/{produto_id}"),
                     sobrescrever=True)


def variante_da_linha(linha):
    produto_id, sku = str(linha.get("providerId") or ""), str(linha.get("sku") or "").strip()
    chave = vinculos.id_variacao(produto_id, sku)
    variante = vinculos.existente("variantes", VarianteProduto, chave) if produto_id else None
    if variante is None and sku:
        variante = VarianteProduto.objects.filter(sku=sku).first()
    if variante is None and produto_id:
        _buscar_no_suri(produto_id)
        variante = vinculos.existente("variantes", VarianteProduto, chave)
        if variante is None:
            produto = vinculos.existente("produtos", Produto, produto_id)
            variante = produto.variante_padrao if produto else None
    return variante


def _quantidade(linha, pedido):
    bruta = Decimal(str(linha.get("quantity") or 1))
    if bruta != bruta.to_integral_value():
        avisar(f"Item {linha.get('sku')} com quantidade {bruta} (fracionada) gravado como "
               f"{max(int(bruta), 1)}; confira o valor no pedido.", recurso="pedidos",
               id=pedido.pk, descricao=pedido.number)
    return max(int(bruta), 1)


def _gravar(item, linha, pedido):
    variante = variante_da_linha(linha)
    quantidade = _quantidade(linha, pedido)
    unitario = valor(linha.get("unitPrice")) or ZERO
    item.variante = variante
    item.produto = variante.produto if variante else None
    item.id_variacao = (variante.pk if item.produto and item.produto.tipo ==
                        Produto.Tipo.VARIAVEL else 0)
    item.nome = str(linha.get("name") or "")[:255]
    item.sku = str(linha.get("sku") or "")[:100]
    item.quantidade = quantidade
    item.preco_unitario = unitario
    subtotal = valor(linha.get("subTotalAmount"))
    # "totalAmout" e "discountAmout" sao os nomes do Suri (com o erro de digitacao).
    total = valor(linha.get("totalAmout"))
    if total is None and subtotal is not None:
        total = dinheiro(subtotal - (valor(linha.get("discountAmout")) or ZERO))
    item.subtotal, item.total = valores_do_item(unitario, quantidade, subtotal, total)
    item.total_desconto = item.subtotal - item.total
    item.imposto_subtotal = item.imposto_total = ZERO
    item.save()
    return item


def gravar_itens(pedido, dados):
    """Cria ou atualiza os itens; o item que sumiu do pedido no Suri sai do hub."""
    atuais = {str(item.pk): item for item in pedido.itens.all()}
    mantidos = set()
    for posicao, linha in enumerate(dados.get("items") or []):
        chave = f"{dados['id']}:{posicao}:{linha.get('sku') or ''}"
        pk = vinculos.objeto_id(ENTIDADE, chave)
        item = _gravar(atuais.get(str(pk)) or ItemPedido(pedido=pedido), linha, pedido)
        vinculos.referenciar(ENTIDADE, chave, item)
        mantidos.add(item.pk)
    if "items" in dados:
        pedido.itens.exclude(pk__in=mantidos).delete()
