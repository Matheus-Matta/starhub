"""Categorias e produtos do Suri Shop no catalogo do hub.

    importar_categorias(cliente.get("shop/categories"))   # arvore: categoria > children
    produto, criado = importar_produto(json_do_produto_suri)

Produto do Suri: preco e estoque ficam em `dimensions` (uma por SKU). Sem `attributes`
o produto e simples (uma dimensao); com eles, variavel, e cada dimensao vira uma
variante com as opcoes de `dimensions` ({"Cor": "Azul", "Tamanho": "M"}). Estoque por
loja do Suri: o hub tem um numero so, a soma das lojas. Peso vem em gramas. A
dimensao que e servico do hub (apps/suri/servicos.py) nao vira variante.
"""

from decimal import Decimal

from django.db import transaction
from django.utils.text import slugify

from apps.core.models import Origin
from apps.loja.dinheiro import ZERO, dinheiro
from apps.loja.models import Categoria, Produto, VarianteProduto
from apps.loja.services.slugs import slug_livre
from apps.loja.services.variantes import obter_variante_padrao
from apps.suri import imagens, vinculos
from apps.suri import servicos as servicos_suri
from apps.suri.contexto import avisar, configuracao_atual
from apps.suri.opcoes import gravar_opcoes
from apps.suri.servicos_dimensoes import SEM_SERVICO

ORIGEM = Origin.SURI


def valor(numero):
    return dinheiro(numero) if numero not in (None, "") else None


def importar_categorias(arvore, pai=None):
    """Cria/atualiza a arvore inteira; devolve {id do Suri: Categoria}."""
    mapa = {}
    for dados in arvore or []:
        obj = vinculos.existente("categorias", Categoria, dados["id"])
        if obj is None:
            slug = slugify(dados.get("name") or "", allow_unicode=True)
            obj = Categoria.objects.filter(slug=slug).first() if slug else None
            obj = obj or Categoria(slug=slug_livre(Categoria, slug or "categoria"), origin=ORIGEM)
        obj.nome = (dados.get("name") or obj.nome or "Categoria Suri")[:200]
        obj.descricao = dados.get("description") or obj.descricao
        obj.pai = pai if pai is not None else obj.pai
        obj.save()
        vinculos.referenciar("categorias", dados["id"], obj)
        mapa[str(dados["id"])] = obj
        mapa |= importar_categorias(dados.get("children"), obj)
    return mapa


def _estoque(dimensao):
    lojas = (dimensao.get("stocks") or {}).values()
    return int(sum((loja or {}).get("stock") or 0 for loja in lojas))


def _sku_livre(variante, sku, produto_dados):
    """SKU de outra variante do hub nao entra: avisa e mantem o da variante."""
    if not sku or sku == variante.sku:
        return
    if VarianteProduto.objects.filter(sku=sku).exclude(pk=variante.pk).exists():
        avisar(f"SKU {sku} do Suri ja e de outra variante no hub; mantido o "
               f"{variante.sku or 'vazio'}.", recurso="produtos", id=variante.produto_id,
               descricao=variante.produto.nome, id_externo=produto_dados.get("id"))
        return
    variante.sku = sku


def _gravar_variante(variante, dimensao, produto_dados, posicao, completa):
    preco = valor(dimensao.get("price"))
    variante.price = preco if preco is not None else valor(produto_dados.get("price")) or ZERO
    promocional = valor(produto_dados.get("promotionalPrice"))
    variante.sale_price = promocional if promocional and promocional < variante.price else None
    variante.inventory_quantity = _estoque(dimensao)
    variante.posicao = posicao
    gramas = (dimensao.get("measurements") or {}).get("weightInGrams")
    if gramas:
        variante.weight = Decimal(str(gramas)) / 1000  # o hub guarda em kg
    if completa:
        _sku_livre(variante, str(dimensao.get("sku") or "").strip()[:100], produto_dados)
        variante.titulo = (" / ".join(str(v) for v in _opcoes(dimensao).values())
                           or "Default")[:255]
    variante.save()
    gravar_opcoes(variante, _opcoes(dimensao))


def _opcoes(dimensao):
    """Opcoes da variante sem o atributo dos servicos: o envio poe "Serviço": "Sem
    serviço" na variacao do produto (envio/produtos_atributos.py); nao e opcao dela."""
    return {nome: valor for nome, valor in (dimensao.get("dimensions") or {}).items()
            if nome not in servicos_suri.atributos()}


def _sem_servicos(dados):
    """(atributos, dimensoes) sem o que o hub mandou como servico; o produto do Suri
    que so tem o atributo "Serviço" continua simples no hub."""
    atributos = dados.get("attributes") or []
    dimensoes = dados.get("dimensions") or [{"sku": dados.get("sku")}]
    configuracao = configuracao_atual()
    if not (getattr(configuracao, "enviar_servicos", False)
            or getattr(configuracao, "receber_servicos", False)):
        return atributos, dimensoes
    produto, de_servico = {"providerId": dados["id"]}, servicos_suri.atributos()
    return ([a for a in atributos if a.get("name") not in de_servico],
            [d for d in dimensoes if servicos_suri.da_linha({**produto, **d}) is None
             and not _com_servico(d, de_servico)])


def _com_servico(dimensao, de_servico):
    # Combinacao cor x servico sem vinculo no hub (banco novo): o valor de um atributo
    # de servico diferente de "Sem serviço" ja diz que nao e variante do produto.
    valores = dimensao.get("dimensions") or {}
    return any(valores.get(nome) not in (None, "", SEM_SERVICO) for nome in de_servico)


def _variantes(produto, dados, completa):
    externo = str(dados["id"])
    atributos, dimensoes = _sem_servicos(dados)
    variavel = bool(atributos)
    for posicao, dimensao in enumerate(dimensoes):
        chave = vinculos.id_variacao(externo, dimensao.get("sku"))
        variante = vinculos.existente("variantes", VarianteProduto, chave)
        if variante is None and not variavel:
            variante = produto.variante_padrao or obter_variante_padrao(produto)
        if variante is None and dimensao.get("sku"):
            variante = produto.variantes.filter(sku=dimensao["sku"]).first()
        nova = variante is None
        variante = variante or VarianteProduto(produto=produto, origin=ORIGEM,
                                               is_default=not produto.variantes.exists())
        _gravar_variante(variante, dimensao, dados, posicao, completa or nova)
        vinculos.referenciar("variantes", chave, variante, pai=externo)


def _categorias(produto, dados):
    ids = [dados.get("categoryId"), dados.get("subcategoryId")]
    categorias = [c for c in (vinculos.existente("categorias", Categoria, i) for i in ids if i)
                  if c]
    if categorias:
        produto.categorias.set(categorias)


@transaction.atomic
def importar_produto(dados, sobrescrever=False, refazer_fotos=False):
    """Produto novo recebe tudo; o existente so preco e estoque, salvo `sobrescrever`.
    `refazer_fotos`: so do Sincronizar (o pedido tambem usa `sobrescrever`)."""
    externo = str(dados["id"])
    obj = vinculos.existente("produtos", Produto, externo)
    criado = obj is None
    if criado:
        obj = Produto(slug=slug_livre(Produto, slugify(dados.get("name") or "produto")),
                      origin=ORIGEM)
    if criado or sobrescrever:
        obj.nome = (dados.get("name") or "Produto Suri")[:255]
        obj.descricao = dados.get("description") or ""
        obj.tipo = Produto.Tipo.VARIAVEL if _sem_servicos(dados)[0] else Produto.Tipo.SIMPLES
        ativo = dados.get("isActive", True)
        obj.status = Produto.Status.PUBLICADO if ativo else Produto.Status.RASCUNHO
        obj.save()
    vinculos.referenciar("produtos", externo, obj)
    _categorias(obj, dados)
    _variantes(obj, dados, criado or sobrescrever)
    if refazer_fotos:
        imagens.refazer(obj, dados)
    else:
        imagens.importar(obj, dados)
    return obj, criado
