"""O que passa do produto simples para o pai no agrupamento (services/agrupar.py).

Sem isto a exclusao do simples levaria fotos (CASCADE), seria barrada pelas avaliacoes
(PROTECT) e tiraria o produto dos itens de pedido (SET_NULL).

Vinculos com as lojas: a variante e as fotos movidas apontavam para o produto ANTIGO da
loja. Mantidos, o update do pai mandaria la o id de uma variante de outro produto e o
envio inteiro falharia; sem eles a loja recebe as variantes e fotos como novas no pai.
O vinculo do produto antigo fica: e por ele que a exclusao (envio depois do commit)
acha o produto na loja para apagar.
"""

from django.db.models import Count

from apps.core.models import ExternalReference, Origin
from apps.loja.models import Avaliacao, ItemPedido, MidiaProduto
from apps.loja.services.inativos import fora_das_lojas

# Id do simples antigo -> variante (a API Woo resolve: o ERP segue mandando o id velho).
ENTIDADE_ID_ANTIGO = "produto_agrupado"
_RELACOES = ("categorias", "tags", "cupons", "cupons_que_excluem", "regras_servico")


def cliente_com_duas_avaliacoes(produtos):
    """E-mail do cliente que avaliou dois dos produtos (o banco aceita 1 por produto)."""
    repetido = (Avaliacao.objects.filter(produto__in=produtos, cliente__isnull=False)
                .values("cliente__email").annotate(total=Count("id"))
                .filter(total__gt=1).order_by("cliente__email").first())
    return repetido["cliente__email"] if repetido else None


def esquecer_na_loja(produto, variante):
    fotos = [str(pk) for pk in MidiaProduto.objects.filter(produto=produto)
             .values_list("pk", flat=True)]
    ExternalReference.objects.filter(entity_type="variantes",
                                     object_id=str(variante.pk)).delete()
    ExternalReference.objects.filter(entity_type="midias", object_id__in=fotos).delete()
    if fora_das_lojas(produto):
        # Inativo nao gera exclusao na loja: o vinculo dele ficaria orfao para sempre.
        ExternalReference.objects.filter(entity_type="produtos",
                                         object_id=str(produto.pk)).delete()
    ExternalReference.objects.update_or_create(
        platform=Origin.API, entity_type=ENTIDADE_ID_ANTIGO, external_id=str(produto.pk),
        defaults={"object_id": str(variante.pk)})


def levar_para_o_pai(produto, base, variante):
    for midia in MidiaProduto.objects.filter(produto=produto):
        # Foto do simples era a foto daquele tamanho/cor: fica presa a variante dele.
        midia.produto, midia.variante_id = base, midia.variante_id or variante.pk
        midia.save()
    for avaliacao in Avaliacao.objects.filter(produto=produto):
        avaliacao.produto = base
        avaliacao.save()
    # update() de proposito: ItemPedido.save so preenche campo vazio, e o pedido antigo
    # nao deve ir de novo as lojas so porque o item trocou de produto.
    ItemPedido.objects.filter(produto=produto).update(produto=base)
    for relacao in _RELACOES:
        getattr(base, relacao).add(*getattr(produto, relacao).all())
