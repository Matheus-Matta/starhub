"""Botao "Agrupar produtos simples" dentro do produto simples (services/agrupar.py).

Trocar o tipo do simples para Variavel mostra a secao Variantes e, nela, o botao. O
dialog (templates/admin/loja/produto/_dialog_agrupar.html, js/agrupar-produtos.js)
busca os outros simples por nome ou SKU, sugere o nome do pai e o valor de cada um e
posta aqui. O produto aberto e o pai: fica com o id, as fotos e o vinculo das lojas.

    GET  <pk>/agrupar/buscar/?q=camiseta      -> {"produtos": [{id, nome, sku, ...}]}
    GET  <pk>/agrupar/sugestao/?ids=13,14     -> {"nome", "itens": [{id, valor}, ...]}
    POST <pk>/agrupar/  produtos, nome, opcao/opcao_id, valor_<id>/valor_id_<id>
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseNotAllowed, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse

from apps.core.models import ExternalReference
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Produto, TipoVariante, ValorVariante
from apps.loja.services.agrupar import AgrupamentoInvalido, agrupar, sugestao

LIMITE_BUSCA = 30


def busca_inicial(produto):
    """O nome sem a ultima palavra: "Camiseta Basica P" ja acha a M e a G ao abrir."""
    palavras = (produto.nome or "").split()
    return " ".join(palavras[:-1] if len(palavras) > 1 else palavras)


def _ids(texto):
    return [int(pk) for pk in str(texto or "").split(",") if pk.strip().isdigit()]


def _cadastros_de_opcoes():
    return [{
        "id": tipo.pk,
        "nome": tipo.nome,
        "valores": [{"id": valor.pk, "nome": valor.valor} for valor in tipo.valores.all()],
    } for tipo in TipoVariante.objects.prefetch_related("valores")]


def _opcao_e_valores(post, ids):
    tipo = None
    if str(post.get("opcao_id") or "").isdigit():
        tipo = TipoVariante.objects.filter(pk=post["opcao_id"]).first()
        if tipo is None:
            raise AgrupamentoInvalido("A opcao escolhida nao existe mais. Escolha outra.")
    opcao = tipo.nome if tipo else post.get("opcao")
    valores = {}
    for pk in ids:
        valor_id = post.get(f"valor_id_{pk}")
        if not str(valor_id or "").isdigit():
            valores[pk] = post.get(f"valor_{pk}", "")
            continue
        valor = ValorVariante.objects.select_related("tipo").filter(pk=valor_id).first()
        if valor is None:
            raise AgrupamentoInvalido("Um valor escolhido nao existe mais. Escolha outro.")
        if tipo is None or valor.tipo_id != tipo.pk:
            raise AgrupamentoInvalido(
                f"{valor.valor} nao pertence a opcao {opcao or 'informada'}."
            )
        valores[pk] = valor.valor
    return opcao, valores


def _lojas_que_nao_apagam(ids_que_saem):
    """Lojas onde algum simples que sai esta publicado e Enviar > Produtos > Excluir esta
    desligado: la o produto antigo fica, duplicando o SKU com a variante nova."""
    plataformas = set(ExternalReference.objects.filter(
        entity_type="produtos", object_id__in=[str(pk) for pk in ids_que_saem],
    ).values_list("platform", flat=True))
    return [c.nome for c in ConfiguracaoIntegracao.objects.filter(
        active=True, plataforma__in=plataformas)
        if not c.habilitado("enviar", "produtos", "delete")]


class AgruparProdutoMixin:
    def get_urls(self):
        rotas = [
            path("<path:object_id>/agrupar/", self.admin_site.admin_view(self.agrupar_view),
                 name="loja_produto_agrupar"),
            path("<path:object_id>/agrupar/buscar/",
                 self.admin_site.admin_view(self.agrupar_buscar_view),
                 name="loja_produto_agrupar_buscar"),
            path("<path:object_id>/agrupar/sugestao/",
                 self.admin_site.admin_view(self.agrupar_sugestao_view),
                 name="loja_produto_agrupar_sugestao"),
        ]
        return [*rotas, *super().get_urls()]

    def pode_agrupar(self, request, produto):
        # "delete" tambem: os simples que ficam vazios sao excluidos.
        return (produto is not None and produto.tipo == Produto.Tipo.SIMPLES
                and self.has_change_permission(request, produto)
                and self.has_delete_permission(request, produto))

    def _pai(self, request, object_id):
        produto = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.pode_agrupar(request, produto):
            raise PermissionDenied
        return produto

    def get_object(self, request, object_id, from_field=None):
        # A secao Variantes (lista_variantes) so recebe o produto, sem a requisicao: a
        # permissao vai marcada nele, e o template do produto le o mesmo atributo.
        produto = super().get_object(request, object_id, from_field)
        if produto is not None:
            produto.pode_agrupar_aqui = self.pode_agrupar(request, produto)
            produto.agrupar_busca = busca_inicial(produto)
        return produto

    def change_view(self, request, object_id, form_url="", extra_context=None):
        contexto = {**(extra_context or {}), "tipos_variante": _cadastros_de_opcoes()}
        return super().change_view(request, object_id, form_url, contexto)

    def agrupar_buscar_view(self, request, object_id):
        pai = self._pai(request, object_id)
        termo = (request.GET.get("q") or "").strip()
        produtos = (Produto.objects.filter(tipo=Produto.Tipo.SIMPLES)
                    .exclude(pk=pai.pk).exclude(status=Produto.Status.LIXEIRA)
                    .prefetch_related("variantes").order_by("pk"))
        if termo:
            produtos = produtos.filter(
                Q(nome__icontains=termo) | Q(variantes__sku__icontains=termo)).distinct()
        return JsonResponse({"produtos": [{
            "id": p.pk, "nome": p.nome, "sku": p.sku or "",
            "preco": "" if p.preco_regular is None else f"{p.preco_regular:.2f}",
            "estoque": p.estoque,
        } for p in produtos[:LIMITE_BUSCA]]})

    def agrupar_sugestao_view(self, request, object_id):
        pai = self._pai(request, object_id)
        outros = list(Produto.objects.filter(pk__in=_ids(request.GET.get("ids")))
                      .exclude(pk=pai.pk).prefetch_related("variantes").order_by("pk"))
        produtos = [pai, *outros]
        nome, valores = sugestao(produtos)
        return JsonResponse({"nome": nome, "itens": [
            {"id": p.pk, "nome": p.nome, "sku": p.sku or "", "valor": valores[p.pk]}
            for p in produtos]})

    def agrupar_view(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        pai = self._pai(request, object_id)
        voltar = HttpResponseRedirect(reverse("admin:loja_produto_change", args=[pai.pk]))
        outros = [pk for pk in _ids(",".join(request.POST.getlist("produtos"))) if pk != pai.pk]
        ids = [pai.pk, *outros]
        lojas = _lojas_que_nao_apagam(outros)
        try:
            opcao, valores = _opcao_e_valores(request.POST, ids)
            agrupar(pai.pk, ids, request.POST.get("nome"), opcao, valores)
        except AgrupamentoInvalido as erro:
            messages.error(request, str(erro))
            return voltar
        messages.success(request, f"{len(ids)} produtos agrupados neste produto, agora "
                                  f"Variavel com {len(ids)} variantes.")
        if lojas:
            messages.warning(request, f"Em {', '.join(lojas)} os produtos antigos continuam na "
                                      "loja (Enviar > Produtos > Excluir esta desligado). "
                                      "Apague-os la para o SKU nao ficar duplicado.")
        return voltar
