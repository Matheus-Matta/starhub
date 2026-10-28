"""Produto do hub no formato do Suri Shop (o PUT do Suri substitui o objeto inteiro).

    {"id", "sku", "categoryId", "subcategoryId", "isActive", "name", "description",
     "price", "promotionalPrice", "images": [{"url"}], "attributes": [{"name", "options"}],
     "dimensions": [{"sku", "dimensions": {"Cor": "Azul"}, "price",
                     "stocks": {"<loja>": {"stock": 3}}, "measurements": {...}}]}

Preco e Decimal ate o JSON (apps/suri/cliente._json escreve o numero exato). Os
servicos do produto vao no fim de "dimensions", um por SKU do servico
(apps/suri/servicos_dimensoes.py), e os attributes saem das dimensions, batendo com
elas (produtos_atributos.py).
"""

from django.templatetags.static import static

from apps.integracoes.url_publica import url_publica
from apps.loja.dinheiro import ZERO
from apps.loja.models import Categoria, MidiaProduto, Produto
from apps.loja.services.variantes import obter_variante_padrao
from apps.suri import servicos_dimensoes
from apps.suri.envio import produtos_atributos, produtos_dimensoes
from apps.suri.envio.base import id_no_suri

CATEGORIA_PADRAO = CATEGORIA_PADRAO_SLUG = "default"
# Foto que o Suri consegue baixar quando o produto nao tem nenhuma: lista ou url vazia
# derrubavam o PUT com "Value cannot be null. (Parameter 'source')".
FOTO_PADRAO = "starhub/img/logo-600.png"


def _opcoes(variante):
    opcoes = variante.opcoes.select_related("valor__tipo")
    return {o.valor.tipo.nome: o.valor.valor for o in opcoes}


def _dimensao(variante, produto_id, loja, configuracao):
    dimensao = {"sku": variante.sku or f"{produto_id}-{variante.pk}",
                "dimensions": _opcoes(variante), "price": variante.price or ZERO,
                "stocks": {loja: {"stock": max(variante.inventory_quantity, 0)}}}
    midia = variante.midias.filter(tipo=MidiaProduto.Tipo.IMAGEM).order_by("posicao", "id").first()
    url = url_publica(configuracao, midia.url) if midia else ""
    return produtos_dimensoes.completar(
        dimensao, variante, url, midia.alt_text if midia else None)


def _categoria_padrao(produto):
    categoria, _ = Categoria.objects.get_or_create(
        slug=CATEGORIA_PADRAO_SLUG,
        defaults={"nome": CATEGORIA_PADRAO, "descricao": "Produtos sem categoria informada."},
    )
    if produto.categoria_id != categoria.pk:
        produto.categoria = categoria
        produto.save(update_fields=["categoria", "updated_at"])
    produto.categorias.add(categoria)
    return categoria


def categorias(enviador_categorias, produto):
    """(categoryId, subcategoryId): o Suri exige a categoria, e ela vai antes se faltar."""
    categoria = produto.categorias.order_by("pai_id", "id").first() or produto.categoria
    if categoria is None:
        categoria = _categoria_padrao(produto)
    externo = enviador_categorias.garantir(categoria)
    if categoria.pai_id:
        return enviador_categorias.garantir(categoria.pai), externo
    return externo, None


def corpo(enviador_categorias, produto, loja, configuracao, servicos=(), enviados=None):
    """`enviados` (dict) recebe as dimensions de servico, para o vinculo."""
    produto_id = id_no_suri("produtos", produto)
    variantes = list(produto.variantes.order_by("posicao", "id"))
    if not variantes:
        variante = obter_variante_padrao(produto)
        produto._variante_padrao_cache = variante
        variantes = [variante]
    padrao = produto.variante_padrao
    categoria, subcategoria = categorias(enviador_categorias, produto)
    imagens = [{"providerId": None, "url": url, "description": m.alt_text or None}
               for m in produto.midias.filter(tipo=MidiaProduto.Tipo.IMAGEM).order_by("posicao")
               if (url := url_publica(configuracao, m.url))]
    if not imagens and (url := url_publica(configuracao, static(FOTO_PADRAO))):
        imagens = [produtos_dimensoes.imagem(url, produto.nome)]
    promocional = padrao.sale_price if padrao and padrao.sale_price else ZERO
    corpo = {
        "id": produto_id, "sku": (padrao.sku if padrao else "") or produto_id,
        "categoryId": categoria, "subcategoryId": subcategoria, "brand": None,
        "sellerId": "all", "sellerName": None,
        "isActive": produto.active and produto.status == Produto.Status.PUBLICADO,
        "name": produto.nome, "description": produto.descricao or "", "url": None,
        "price": padrao.price if padrao else ZERO, "promotionalPrice": promocional,
        "hasShippingRestriction": False, "images": imagens, "weightInGrams": 0,
        "dimensions": [_dimensao(v, produto_id, loja, configuracao) for v in variantes],
    }
    produtos_atributos.distinguir(corpo["dimensions"], variantes)
    if servicos:
        corpo["dimensions"], de_servico = servicos_dimensoes.dimensoes(
            servicos, corpo["dimensions"], corpo["sku"], configuracao)
        if enviados is not None:
            enviados.update(de_servico)
    if imagens:
        produtos_dimensoes.sem_foto_usa(corpo["dimensions"], imagens[0])
    corpo["attributes"] = produtos_atributos.alinhar(corpo["dimensions"])
    return corpo
