"""line_items, shipping_lines e fee_lines recebidos do ERP.

Como no Woo: linha com "id" altera a existente, sem "id" cria. Para remover uma
linha, mande o "id" com "quantity": 0 (itens) ou "method_id"/"name" nulo (frete/taxa).
"""

from apps.loja.dinheiro import ValorInvalido, dinheiro
from apps.loja.dinheiro import texto as dinheiro_texto
from apps.loja.models import ItemPedido, Produto, VarianteProduto
from apps.loja.totais import valores_do_item
from apps.woo_api import metadados
from apps.woo_api.erros import WooErro, parametro_invalido
from apps.woo_api.recursos.base import inteiro, texto
from apps.woo_api.recursos.pedidos_meta import separar_servicos
from apps.woo_api.recursos.pedidos_servicos import separar_starhub


def _valor(linha, campo, grupo):
    try:
        return dinheiro(linha.get(campo))
    except ValorInvalido as erro:
        raise parametro_invalido(grupo, f"{campo}: {erro}") from erro


def _lista(dados, campo):
    linhas = dados.get(campo)
    if not isinstance(linhas, list) or not all(isinstance(li, dict) for li in linhas):
        raise parametro_invalido(campo, f"{campo} deve ser uma lista de objetos.")
    return linhas


def _produto(linha):
    produto_id = inteiro(linha.get("product_id") or 0, "line_items")
    if not produto_id:
        return None
    produto = Produto.objects.filter(pk=produto_id).first()
    if produto is None:
        raise WooErro("woocommerce_rest_invalid_product_id",
                      f"Produto {produto_id} nao existe.", 400)
    return produto


def _variante(produto, id_variacao):
    """A unidade vendida: a variacao pedida, ou a variante padrao do produto."""
    if produto is None:
        return None
    if id_variacao:
        variante = VarianteProduto.objects.filter(pk=id_variacao, produto=produto).first()
        if variante is not None:
            return variante
    return produto.variante_padrao


def _gravar_item(pedido, linha, item):
    quantidade = inteiro(linha.get("quantity", item.quantidade), "line_items")
    item.id_variacao = inteiro(linha.get("variation_id", item.id_variacao) or 0, "line_items")
    if "product_id" in linha or "variation_id" in linha or item.pk is None:
        if "product_id" in linha or item.pk is None:
            item.produto = _produto(linha)
        item.variante = _variante(item.produto, item.id_variacao)
    produto = item.produto
    item.quantidade = quantidade
    item.nome = texto(linha.get("name") or item.nome or (produto.nome if produto else ""),
                      "line_items", 255)
    item.sku = texto(linha.get("sku") or item.sku or (produto.sku if produto else ""),
                     "line_items", 100)
    if "tax_class" in linha:
        item.classe_fiscal = texto(linha["tax_class"], "line_items", 100)
    recalcular = item.pk is None or "quantity" in linha or "product_id" in linha
    subtotal = _valor(linha, "subtotal", "line_items")
    total = _valor(linha, "total", "line_items")
    if recalcular or subtotal is not None or total is not None:
        preco = item.variante.current_price if item.variante else None
        item.subtotal, item.total = valores_do_item(preco, quantidade, subtotal, total)
    for campo, atributo in (("subtotal_tax", "imposto_subtotal"), ("total_tax", "imposto_total")):
        if linha.get(campo) not in (None, ""):
            setattr(item, atributo, _valor(linha, campo, "line_items"))
    servicos = None
    if "meta_data" in linha:
        # O starhub e o formato que o GET devolve; se vier junto com EPOFW, ele manda.
        do_starhub, resto = separar_starhub(linha["meta_data"])
        do_epofw, resto = separar_servicos(resto)
        servicos = do_epofw if do_starhub is None else do_starhub
        item.metadados = metadados.mesclar(item.metadados, resto)
    item.pedido = pedido
    item.save()
    # item_id so existe depois do save; o formato e o mesmo que o Shopify grava.
    return None if servicos is None else [
        {"item_id": item.pk, "sku": item.sku, **servico} for servico in servicos]


def gravar_itens(pedido, dados):
    """Grava os itens e devolve {item_id: servicos} das linhas que trouxeram servicos."""
    por_item = {}
    existentes = {item.pk: item for item in pedido.itens.all()}
    for linha in _lista(dados, "line_items"):
        if linha.get("id"):
            item = existentes.get(inteiro(linha["id"], "line_items"))
            if item is None:
                raise parametro_invalido("line_items", f"Item {linha['id']} nao e deste pedido.")
            if linha.get("quantity") in (0, "0") or ("product_id" in linha and
                                                     linha["product_id"] is None):
                item.delete()
                continue
        else:
            item = ItemPedido()
        servicos = _gravar_item(pedido, linha, item)
        if servicos is not None:
            por_item[item.pk] = servicos
    return por_item


def gravar_linhas(atuais, dados, campo, campo_chave):
    """Frete (campo_chave=method_id) e taxas (campo_chave=name) guardados como JSON."""
    lista = [dict(linha) for linha in (atuais or [])]
    proximo = max((linha.get("id", 0) for linha in lista), default=0) + 1
    for linha in _lista(dados, campo):
        alvo = next((x for x in lista if linha.get("id") and x.get("id") == linha["id"]), None)
        if alvo is not None and campo_chave in linha and linha[campo_chave] is None:
            lista.remove(alvo)
            continue
        if alvo is None:
            alvo = {"id": proximo, "total_tax": "0.00", "taxes": [], "meta_data": []}
            proximo += 1
            lista.append(alvo)
        for chave, valor in linha.items():
            if chave in ("total", "total_tax"):
                alvo[chave] = dinheiro_texto(_valor(linha, chave, campo) or dinheiro("0"))
            elif chave != "id":
                alvo[chave] = valor
        alvo.setdefault("total", "0.00")
    return lista
