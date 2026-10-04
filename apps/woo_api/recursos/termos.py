"""Categorias, tags e cupons que chegam dentro do produto/pedido: se nao existem, nascem.

O ERP manda {"id": 5}, {"name": "Roupas"} ou {"slug": "roupas"}. O id vale se existir;
senao procuramos pelo nome/slug e, nao achando, criamos. Quem segura duas criacoes
ao mesmo tempo e o indice unico (slug da categoria, nome da tag, nome do cupom):
por isso get_or_create pela chave do indice, e nao um `if not exists`.
"""

from django.utils.text import slugify

from apps.core.models import Origin
from apps.loja.dinheiro import ValorInvalido, dinheiro
from apps.loja.models import Categoria, Cupom, Tag
from apps.woo_api.erros import parametro_invalido
from apps.woo_api.recursos.base import inteiro, texto


def _itens(dados, campo):
    if not isinstance(dados[campo], list):
        raise parametro_invalido(campo, f"{campo} nao e do tipo array.")
    for item in dados[campo]:
        # Tag tambem pode vir como texto solto ("verao"); categoria so como objeto.
        yield item if isinstance(item, dict) else {"name": item}


def _pelo_id(modelo, item, campo):
    if item.get("id") in (None, "", 0, "0"):
        return None
    return modelo.objects.filter(pk=inteiro(item["id"], campo)).first()


def _categoria(item):
    categoria = _pelo_id(Categoria, item, "categories")
    nome = texto(item.get("name"), "categories", 200).strip()
    slug = slugify(str(item.get("slug") or nome), allow_unicode=True)
    if categoria or not slug:
        return categoria
    categoria = Categoria.objects.filter(nome__iexact=nome).order_by("pk").first() if nome \
        else None
    if categoria is None:
        categoria, _ = Categoria.objects.get_or_create(
            slug=slug, defaults={"nome": nome or slug, "origin": Origin.API})
    return categoria


def _tag(item):
    tag = _pelo_id(Tag, item, "tags")
    nome = texto(item.get("name"), "tags", 100).strip()
    if tag or not nome:
        return tag
    tag, _ = Tag.objects.get_or_create(
        nome_normalizado=nome.casefold(),
        defaults={"nome": nome, "slug": slugify(nome), "origin": Origin.API})
    return tag


def categorias_do_produto(dados):
    return list(filter(None, (_categoria(item) for item in _itens(dados, "categories"))))


def tags_do_produto(dados):
    return list(filter(None, (_tag(item) for item in _itens(dados, "tags"))))


def cadastrar_cupons(linhas):
    """Cupom do pedido que o hub nao conhece vira cadastro em rascunho.

    Rascunho porque o valor veio de um pedido, e nao de uma regra revisada: ativo,
    ele iria para as lojas com um desconto que ninguem conferiu. O cupom e
    identificado pelo nome (= codigo que o ERP mandou); o codigo interno e aleatorio.
    """
    for linha in linhas:
        codigo = texto(linha.get("code"), "coupon_lines", 100).strip()
        if not codigo or Cupom.objects.filter(name__iexact=codigo).exists():
            continue
        try:
            valor = dinheiro(linha.get("discount")) or dinheiro("0")
        except ValorInvalido as erro:
            raise parametro_invalido("coupon_lines", f"discount: {erro}") from erro
        Cupom.objects.get_or_create(name=codigo, defaults={
            "discount_type": Cupom.TipoDesconto.VALOR_FIXO, "value": valor,
            "status": Cupom.Status.RASCUNHO, "origin": Origin.API,
        })
