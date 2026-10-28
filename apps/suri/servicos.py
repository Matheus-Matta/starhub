"""Servicos do hub no Suri Shop, que nao tem servico: cada um vira dimension do produto.

A dimension sai de servicos_dimensoes.py, com o SKU do servico. Cada uma ganha o
vinculo "servicos" ("<produto>:<sku do servico>" -> Servico, pai = produto, metadata
{"variante", "preco"}): o pedido volta a ser o item da variante padrao com o servico a
parte (importar_itens.py), a baixa de estoque acha as dimensions de servico do produto
(envio/produtos.py), e o reenvio acha o produto quando a regra muda (servicos_sinais.py).

So com Integracoes > Suri > "enviar servicos como variantes" ligado. O PUT do Suri
troca o produto inteiro: produto que saiu da regra vai sem o servico e ele some la.
"""

from decimal import Decimal, InvalidOperation

from apps.core.models import ExternalReference
from apps.loja.models import CategoriaServico, Servico
from apps.suri import vinculos
from apps.suri.servicos_dimensoes import ATRIBUTO

# Nomes usados antes das categorias continuam reconhecidos ao importar o catalogo.
ATRIBUTOS = {ATRIBUTO, "Serviços", "Servico"}
ENTIDADE = "servicos"


def atributos():
    """Nomes de atributo do Suri que sao servico, nunca opcao da variante."""
    return ATRIBUTOS | set(CategoriaServico.objects.values_list("nome", flat=True))


def do_produto(configuracao, produto):
    """[(servico, preco)] que vao como variante; vazio com o envio desligado."""
    if not getattr(configuracao, "enviar_servicos", False):
        return []
    return [(servico, preco) for servico, preco in produto.servicos
            if not servico.ignorado_em("suri")]


def _do_produto_no_suri(produto_id):
    return ExternalReference.objects.filter(
        platform=vinculos.PLATAFORMA, entity_type=ENTIDADE, external_parent_id=str(produto_id))


def vincular(produto_id, enviados):
    """Grava cada servico que foi e apaga o vinculo do que saiu do produto."""
    chaves = []
    for sku, enviado in enviados.items():
        chave = vinculos.id_variacao(produto_id, sku)
        vinculos.referenciar(ENTIDADE, chave, enviado["servico"], pai=produto_id, metadata={
            "variante": enviado["variante"], "preco": f"{enviado['preco']:.2f}"})
        chaves.append(chave)
    _do_produto_no_suri(produto_id).exclude(external_id__in=chaves).delete()


def da_dimensao(linha):
    """(SKU da variante, servico, preco) da linha que e a dimension de um servico."""
    chave = vinculos.id_variacao(str(linha.get("providerId") or ""),
                                 str(linha.get("sku") or "").strip())
    referencia = ExternalReference.objects.filter(
        platform=vinculos.PLATAFORMA, entity_type=ENTIDADE, external_id=chave).values(
        "object_id", "metadata").first()
    if referencia is None:
        return None
    metadata = referencia["metadata"] or {}
    servico = Servico.objects.filter(pk=referencia["object_id"]).first()
    try:
        preco = Decimal(str(metadata["preco"]))
    except (KeyError, InvalidOperation):
        return None  # vinculo de antes, sem preco: a linha segue como servico avulso
    if servico is None or not metadata.get("variante"):
        return None
    return metadata["variante"], servico, preco


def skus_dos_servicos(produto_id):
    """SKUs das dimensions de servico do produto no Suri."""
    chaves = _do_produto_no_suri(produto_id).order_by("external_id").values_list(
        "external_id", flat=True)
    return [chave.partition(":")[2] for chave in chaves]


def desvincular(produto_id):
    _do_produto_no_suri(produto_id).delete()


def produtos_no_suri(servico_id):
    """Ids no Suri dos produtos que levam o servico como variante hoje."""
    return set(ExternalReference.objects.filter(
        platform=vinculos.PLATAFORMA, entity_type=ENTIDADE, object_id=str(servico_id))
        .values_list("external_parent_id", flat=True))


def da_linha(linha):
    """Servico do item do pedido do Suri: pelo vinculo da variante, depois pelo SKU."""
    produto_id, sku = str(linha.get("providerId") or ""), str(linha.get("sku") or "").strip()
    if not sku:
        return None
    servico = vinculos.existente(ENTIDADE, Servico, vinculos.id_variacao(produto_id, sku))
    return (servico or Servico.objects.filter(nome__iexact=sku).first()
            or Servico.objects.filter(sku=sku).first())
