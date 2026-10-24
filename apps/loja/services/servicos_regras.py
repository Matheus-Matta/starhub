"""Quais servicos valem para um produto e por qual preco (RegraServico).

    produtos_da_regra(regra)      -> produtos que a regra pega
    servicos_do_produto(produto)  -> [(servico, preco)] para o produto

A regra por categoria pega as categorias E a faixa de preco (pelo preco normal da
variante padrao); a por produto, so os produtos escolhidos. Para cada produto vale
a primeira regra ativa que casa, pela ordem; o preco dela, ou o padrao do servico.
"""

from django.db.models import Max, Q

from apps.loja.models import Produto, RegraServico

PASSO = 10  # nova regra vai para o fim, com folga para encaixar outra no meio


def proxima_ordem(servico):
    ultima = RegraServico.objects.filter(servico=servico).aggregate(m=Max("ordem"))["m"]
    return PASSO if ultima is None else ultima + PASSO


def _por_categoria(regra):
    """Categoria E faixa de preco (o que estiver preenchido); None sem nenhum dos dois."""
    filtro, usado = Q(), False
    categorias = list(regra.categorias.values_list("pk", flat=True))
    if categorias:
        filtro &= Q(categorias__in=categorias)
        usado = True
    if regra.preco_de is not None or regra.preco_ate is not None:
        filtro &= Q(variantes__is_default=True)
        if regra.preco_de is not None:
            filtro &= Q(variantes__price__gte=regra.preco_de)
        if regra.preco_ate is not None:
            filtro &= Q(variantes__price__lte=regra.preco_ate)
        usado = True
    return filtro if usado else None


def _filtro(regra):
    if regra.tipo == RegraServico.Tipo.PRODUTO:
        escolhidos = list(regra.produtos.values_list("pk", flat=True))
        filtro = Q(pk__in=escolhidos) if escolhidos else None
    else:
        filtro = _por_categoria(regra)
    if filtro is None:
        return Produto.objects.none()
    return Produto.objects.exclude(status=Produto.Status.LIXEIRA).filter(filtro).distinct()


def produtos_da_regra(regra):
    return _filtro(regra).order_by("nome")


def _regras_ativas():
    return (RegraServico.objects.filter(active=True, servico__active=True)
            .select_related("servico").order_by("servico__nome", "ordem", "pk"))


def servicos_do_produto(produto):
    """[(servico, preco)] na ordem do nome do servico; cada servico uma vez so."""
    saida, vistos = [], set()
    for regra in _regras_ativas():
        if regra.servico_id in vistos:
            continue
        if _filtro(regra).filter(pk=produto.pk).exists():
            vistos.add(regra.servico_id)
            saida.append((regra.servico, regra.preco if regra.preco is not None
                          else regra.servico.preco))
    return saida


def separar_regras_por_tipo(regra_model):
    """Regra antiga misturava categoria, faixa e produto; agora e um tipo so (migration).

    Recebe a classe para rodar com o model historico. So produto: vira "por produto".
    Produto junto com categoria ou faixa: os produtos saem para uma regra "por
    produto" nova, com a mesma ordem e preco, e nenhum produto perde o servico.
    Devolve quantas regras novas nasceram.
    """
    novas = 0
    for regra in regra_model.objects.prefetch_related("produtos", "categorias"):
        produtos = list(regra.produtos.all())
        if not produtos:
            continue
        resto = regra.categorias.exists() or regra.preco_de is not None or (
            regra.preco_ate is not None)
        if not resto:
            regra.tipo = "produto"
            regra.save(update_fields=["tipo"])
            continue
        copia = regra_model.objects.create(
            account_id=regra.account_id, servico_id=regra.servico_id, tipo="produto",
            ordem=regra.ordem, preco=regra.preco, active=regra.active)
        copia.produtos.set(produtos)
        regra.produtos.clear()
        novas += 1
    return novas
