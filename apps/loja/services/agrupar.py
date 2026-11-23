"""Agrupa produtos simples num produto variavel (Produtos > acao "Agrupar em variavel").

O ERP so cadastra produto simples: a Camiseta P, M, G e GG chega como quatro produtos.
Aqui um deles (o escolhido como pai) vira Variavel e recebe as variantes dos outros,
que mudam de produto SEM ser recriadas: mesmo id, SKU, preco, estoque e codigo de
barras. Cada variante ganha o valor da opcao (Tamanho: P). Os simples que ficam vazios
sao excluidos depois de passar pedidos, fotos e avaliacoes ao pai
(services/agrupar_mover.py), e a exclusao chega as lojas pelo envio normal.

    nome, valores = sugestao(produtos)       # ("Camiseta Basica", {12: "P", 13: "M"})
    pai = agrupar(12, [12, 13], "Camiseta Basica", "Tamanho", {12: "P", 13: "M"})
"""

from django.db import transaction

from apps.loja.models import (
    Produto,
    TipoVariante,
    ValorDaVarianteProduto,
    ValorVariante,
    VarianteProduto,
)
from apps.loja.services import agrupar_mover as mover


class AgrupamentoInvalido(Exception):
    """A mensagem vai direto ao operador: diz o que corrigir antes de tentar de novo."""


def sugestao(produtos):
    """(nome do pai, {pk: valor}): as palavras iguais no comeco de todos os nomes formam
    o nome; o resto de cada um e o valor da opcao. So o comeco: juntar tambem o fim
    igual tirava do meio o "2" de "SOFA 2 LUGARES" e o nome ficava sem sentido."""
    nomes = [(p.nome or "").split() for p in produtos]
    if not nomes:
        return "", {}
    menor = min(len(n) for n in nomes)
    inicio = 0
    while inicio < menor and len({n[inicio] for n in nomes}) == 1:
        inicio += 1
    nome = " ".join(nomes[0][:inicio])
    valores = {p.pk: " ".join(n[inicio:]) for p, n in zip(produtos, nomes, strict=True)}
    return nome or (produtos[0].nome or ""), valores


def _conferir_pedido(base_id, ids, nome, opcao):
    if len(ids) < 2:
        raise AgrupamentoInvalido("Escolha pelo menos dois produtos simples para agrupar.")
    if base_id not in ids:
        raise AgrupamentoInvalido("O produto pai precisa ser um dos produtos escolhidos.")
    if not nome:
        raise AgrupamentoInvalido("Informe o nome do produto variavel.")
    if not opcao:
        raise AgrupamentoInvalido("Informe o nome da opcao (ex.: Tamanho, Cor, Voltagem).")


def _conferir_produtos(produtos, ids, valores):
    if len(produtos) != len(ids):
        raise AgrupamentoInvalido(
            "Algum produto escolhido nao existe mais (ja foi agrupado ou excluido). "
            "Volte a lista de produtos e selecione de novo.")
    vistos = {}
    for produto in produtos:
        if produto.tipo != Produto.Tipo.SIMPLES:
            raise AgrupamentoInvalido(
                f"{produto.nome} e {produto.get_tipo_display()}: so produto simples entra "
                "no agrupamento. Tire ele da selecao.")
        valor = valores[produto.pk]
        if not valor:
            raise AgrupamentoInvalido(f"Informe o valor da opcao de {produto.nome}.")
        anterior = vistos.setdefault(valor.casefold(), produto)
        if anterior is not produto:
            raise AgrupamentoInvalido(
                f"O valor {valor} esta repetido em {anterior.nome} e {produto.nome}: cada "
                "variante precisa de um valor diferente.")


def _variante_unica(produto):
    variantes = list(VarianteProduto.objects.select_for_update().filter(produto=produto))
    if len(variantes) != 1:
        raise AgrupamentoInvalido(
            f"{produto.nome} tem {len(variantes)} variantes; o produto simples precisa de "
            "exatamente uma. Corrija o cadastro dele e agrupe de novo.")
    return variantes[0]


def _valor(tipo, texto):
    existente = ValorVariante.objects.filter(tipo=tipo, valor_normalizado=texto.casefold())
    return existente.first() or ValorVariante.objects.create(tipo=tipo, valor=texto)


def _tipo(nome):
    # O tipo e da conta toda (Cor serve a qualquer produto): reaproveita "tamanho" = "Tamanho".
    return (TipoVariante.objects.filter(nome__iexact=nome).first()
            or TipoVariante.objects.create(nome=nome))


def agrupar(base_id, ids, nome, opcao, valores):
    """Devolve o produto pai, ja Variavel. Erro de cadastro vira AgrupamentoInvalido e
    nada muda (tudo numa transacao)."""
    ids = sorted({int(pk) for pk in ids})
    base_id, nome, opcao = int(base_id), (nome or "").strip(), (opcao or "").strip()
    limpos = {pk: (valores.get(pk) or "").strip()[:100] for pk in ids}
    _conferir_pedido(base_id, ids, nome, opcao)
    with transaction.atomic():
        # Lock em ordem de id e releitura: dois agrupamentos com o mesmo produto ao mesmo
        # tempo, o segundo espera e ve que o produto ja foi levado.
        produtos = list(Produto.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
        _conferir_produtos(produtos, ids, limpos)
        variantes = {p.pk: _variante_unica(p) for p in produtos}
        base = next(p for p in produtos if p.pk == base_id)
        outros = [p for p in produtos if p.pk != base_id]
        email = mover.cliente_com_duas_avaliacoes(produtos)
        if email:
            raise AgrupamentoInvalido(
                f"O cliente {email} avaliou mais de um destes produtos, e o produto variavel "
                "aceita uma avaliacao por cliente. Exclua uma das avaliacoes dele e agrupe "
                "de novo.")
        base.tipo, base.nome = Produto.Tipo.VARIAVEL, nome[:255]
        base.save()
        tipo = _tipo(opcao[:100])
        for posicao, produto in enumerate([base, *outros]):
            variante = variantes[produto.pk]
            if produto is not base:
                mover.esquecer_na_loja(produto, variante)
                variante.produto, variante.is_default = base, False
            variante.titulo, variante.posicao = limpos[produto.pk], posicao
            variante.save()
            variante.opcoes.all().delete()
            ValorDaVarianteProduto.objects.create(
                variante=variante, valor=_valor(tipo, limpos[produto.pk]))
        for produto in outros:
            mover.levar_para_o_pai(produto, base, variantes[produto.pk])
            produto.delete()
    return base
