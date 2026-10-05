"""Categorias, tags e os campos de variante vindos da API do WooCommerce.

    categoria, criada = importar_categoria({"id": 9, "name": "Sofas", "slug": "sofas",
                                            "parent": 0, "description": "", "image": None})

Categoria ja vinculada so atualiza o que mudou na loja; sem vinculo, o mesmo slug no
hub e a mesma categoria (o vinculo nasce). A categoria pai vem pelo id do Woo.
"""

from decimal import Decimal, InvalidOperation

from django.utils.text import slugify

from apps.core.models import Origin
from apps.loja.dinheiro import ValorInvalido, dinheiro
from apps.loja.models import Categoria, Tag, VarianteProduto
from apps.loja.services.slugs import slug_livre
from apps.woocommerce import vinculos
from apps.woocommerce.imagens import ImagemErro, baixar

ORIGEM = Origin.WOOCOMMERCE


def preco(valor):
    """Texto do Woo ("19.90", "") em Decimal com 2 casas; vazio ou invalido = None."""
    try:
        return dinheiro(str(valor).strip()) if valor not in (None, "") else None
    except ValorInvalido:
        return None


def campos_variante(dados, posicao=0):
    """Campos de VarianteProduto de um produto simples ou de uma variacao do Woo."""
    campos = {"price": preco(dados.get("regular_price")) or preco(dados.get("price")) or
              Decimal("0.00"),
              "sale_price": preco(dados.get("sale_price")),
              "inventory_quantity": int(dados.get("stock_quantity") or 0),
              "posicao": posicao}
    if isinstance(dados.get("manage_stock"), bool):  # "parent" na variacao = herda
        campos["manage_inventory"] = dados["manage_stock"]
    if dados.get("stock_status") in VarianteProduto.SituacaoEstoque.values:
        campos["stock_status"] = dados["stock_status"]
    if dados.get("backorders"):
        campos["inventory_policy"] = "deny" if dados["backorders"] == "no" else "continue"
    try:
        if dados.get("weight") not in (None, ""):
            campos["weight"] = Decimal(str(dados["weight"]).replace(",", "."))
    except InvalidOperation:
        pass
    return campos


def _imagem(categoria, imagem):
    if not imagem or not imagem.get("src") or categoria.imagem:
        return
    try:
        categoria.imagem = {"src": baixar(imagem["src"]), "alt": imagem.get("alt") or ""}
    except ImagemErro:
        return  # categoria sem foto nao e erro; a proxima sincronizacao tenta de novo


def importar_categoria(dados, todas=None):
    """`todas`: {id do Woo: dados} da sincronizacao, para achar a pai que vem depois."""
    externo = dados["id"]
    obj = vinculos.existente("categorias", Categoria, externo)
    criada = obj is None
    if criada:
        slug = slugify(dados.get("slug") or dados.get("name") or "", allow_unicode=True)
        obj = Categoria.objects.filter(slug=slug).first() if slug else None
        criada = obj is None
        obj = obj or Categoria(slug=slug_livre(Categoria, slug or dados.get("name")),
                               origin=ORIGEM)
    obj.nome = (dados.get("name") or obj.nome or "Categoria WooCommerce")[:200]
    obj.descricao = dados.get("description") or obj.descricao
    pai_id = dados.get("parent") or 0
    if pai_id:
        pai = vinculos.existente("categorias", Categoria, pai_id)
        if pai is None and todas and pai_id in todas:
            pai = importar_categoria(todas[pai_id], todas)[0]
        obj.pai = pai if pai and pai.pk != obj.pk else obj.pai
    _imagem(obj, dados.get("image"))
    obj.save()
    vinculos.referenciar("categorias", externo, obj)
    return obj, criada


def categorias_do_produto(itens):
    """[Categoria] dos {"id", "name", "slug"} do produto; cria a que faltar."""
    return [importar_categoria(item)[0] for item in itens or [] if item.get("id")]


def tags_do_produto(itens):
    tags = []
    for item in itens or []:
        nome = (item.get("name") or "").strip()[:100]
        if not nome:
            continue
        tag = (Tag.objects.filter(nome_normalizado=nome.casefold()).first()
               or Tag.objects.create(nome=nome, slug=slug_livre(Tag, item.get("slug") or nome),
                                     origin=ORIGEM))
        tags.append(tag)
    return tags
