"""Um registro e os que pertencem a ele, para os botoes Logs, Tarefas e Historico.

    registros.chave(produto)               # "12-345" (content_type-pk), vai na URL
    alvo = registros.alvo("12-345")        # {ct_produto: {"345"}, ct_variante: {...}, ...}
    LogEntry.objects.filter(registros.filtro(alvo))

A variante abre num modal sem botoes: so pelo produto o operador chega nela. Por isso
o filtro inclui os filhos que morrem junto com o registro (FK com CASCADE: variantes,
midias, itens do pedido, enderecos do cliente) ate PROFUNDIDADE niveis, e os vinculos
com os marketplaces (ExternalReference), onde fica o id e o estado de cada loja.
FK com PROTECT/SET_NULL (pedido -> cliente, avaliacao -> produto) nao entra: e outro
registro, com os botoes dele.

"so:12-345" e so o registro, sem os relacionados.
"""

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q

PROFUNDIDADE = 2
LIMITE = 2000  # por model: produto com milhares de midias nao vira uma consulta gigante
SO = "so:"

# entity_type do ExternalReference de cada model (apps/integracoes/vinculos.py).
ENTIDADES_EXTERNAS = {
    "loja.produto": ("produtos",), "loja.varianteproduto": ("variantes",),
    "loja.pedido": ("pedidos",), "loja.itempedido": ("itens_pedido",),
    "loja.cliente": ("clientes",), "loja.clienteendereco": ("enderecos_cliente",),
    "loja.categoria": ("categorias",), "loja.cupom": ("cupons",),
    "loja.midiaproduto": ("midias",),
}


def chave(obj):
    return f"{ContentType.objects.get_for_model(type(obj)).pk}-{obj.pk}"


def separar(valor):
    """("12", "345", com_relacionados) ou (None, None, False) se o valor nao presta."""
    valor = valor or ""
    so = valor.startswith(SO)
    tipo, _, pk = valor.removeprefix(SO).partition("-")  # pk UUID tem "-": so o 1o separa
    if not tipo.isdigit() or not pk:
        return None, None, False
    return int(tipo), pk, not so


def _eh_historico(modelo):
    return hasattr(modelo, "instance_type")  # versao do simple_history


def _filhos(modelo, pks, alvo, nivel):
    if not nivel or not pks:
        return
    for relacao in modelo._meta.related_objects:
        filho = relacao.related_model
        dono = (relacao.one_to_many or relacao.one_to_one) and relacao.on_delete is models.CASCADE
        if not dono or _eh_historico(filho):
            continue
        ids = list(filho._base_manager.filter(**{f"{relacao.field.name}__in": pks})
                   .values_list("pk", flat=True)[:LIMITE])
        if not ids:
            continue
        tipo = ContentType.objects.get_for_model(filho).pk
        alvo.setdefault(tipo, set()).update(str(i) for i in ids)
        _filhos(filho, ids, alvo, nivel - 1)


def _externos(alvo):
    from apps.core.models import ExternalReference

    consulta = Q()
    for tipo, pks in alvo.items():
        modelo = ContentType.objects.get_for_id(tipo)
        entidades = ENTIDADES_EXTERNAS.get(f"{modelo.app_label}.{modelo.model}")
        if entidades:
            consulta |= Q(entity_type__in=entidades, object_id__in=list(pks))
    if not consulta:
        return
    ids = ExternalReference._base_manager.filter(consulta).values_list("pk", flat=True)[:LIMITE]
    if ids:
        tipo = ContentType.objects.get_for_model(ExternalReference).pk
        alvo.setdefault(tipo, set()).update(str(i) for i in ids)


def alvo(valor):
    """{content_type_id: {pks}} do valor da URL; {} se invalido."""
    tipo, pk, com_relacionados = separar(valor)
    if tipo is None:
        return {}
    resultado = {tipo: {pk}}
    modelo = ContentType.objects.filter(pk=tipo).first()
    classe = modelo.model_class() if modelo else None
    if com_relacionados and classe is not None:
        _filhos(classe, [pk], resultado, PROFUNDIDADE)
        _externos(resultado)
    return resultado


def filtro(alvo_, campo_tipo="content_type_id", campo_pk="object_pk"):
    """Q que acha qualquer um dos registros do alvo; vazio nao acha nada."""
    consulta = Q(pk__in=[])
    for tipo, pks in alvo_.items():
        consulta |= Q(**{campo_tipo: tipo, f"{campo_pk}__in": sorted(pks)})
    return consulta


def nome(valor):
    """"Produto: Camiseta" para o filtro aplicado; o registro pode ja ter sido excluido."""
    tipo, pk, _ = separar(valor)
    modelo = ContentType.objects.filter(pk=tipo).first() if tipo else None
    if modelo is None:
        return "Registro invalido"
    classe = modelo.model_class()
    obj = classe._base_manager.filter(pk=pk).first() if classe else None
    return f"{modelo.name.capitalize()}: {obj if obj is not None else f'#{pk}'}"
