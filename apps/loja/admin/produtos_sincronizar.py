""""Sincronizar com integracao": acao em massa na lista e botao dentro do produto.

Um dialog pergunta para qual integracao ativa (Shopify, Suri, WooCommerce...) e cria
uma tarefa de Exportar so com os produtos escolhidos: os dados do produto (create se
ainda nao esta na loja, update se ja esta) e depois o estoque das variantes. E o mesmo
`exportar_dados` da tela "Sincronizar loja" (vinculo, lock, permissoes, progresso,
falhas e Retomar iguais), sem precisar editar o produto para ele ir de novo.

A acao da lista recebe a integracao escolhida no dialog no campo "integracao" do
POST (static/starhub/js/sincronizar-produtos.js); o botao do produto posta na rota
"<pk>/sincronizar/".
"""

from django.contrib import admin, messages
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from apps.integracoes import sincronizacao
from apps.integracoes.admin_sincronizacao import url_execucao
from apps.integracoes.models import ConfiguracaoIntegracao


def _permitidos(configuracao):
    return {i["recurso"]: i for i in
            sincronizacao.recursos_disponiveis(configuracao, sincronizacao.EXPORTAR)}


def integracoes_do_dialog():
    """[{pk, nome, plataforma, permitido, motivo, estoque}] das integracoes ativas."""
    saida = []
    for configuracao in ConfiguracaoIntegracao.objects.filter(active=True).order_by(
            "plataforma", "nome"):
        itens = _permitidos(configuracao)
        produtos, estoque = itens.get("produtos", {}), itens.get("estoque", {})
        saida.append({
            "pk": configuracao.pk, "nome": configuracao.nome,
            "plataforma": configuracao.get_plataforma_display(),
            "permitido": bool(produtos.get("permitido")),
            "motivo": produtos.get("motivo") or "Envio de produtos indisponivel",
            "estoque": bool(estoque.get("permitido")),
        })
    return saida


def sincronizar(request, ids, configuracao_id, voltar):
    """Cria a tarefa e devolve o redirect (para a tarefa, ou `voltar` com o erro)."""
    configuracao = ConfiguracaoIntegracao.objects.filter(
        pk=configuracao_id or None, active=True).first() if str(configuracao_id).isdigit() \
        else None
    if configuracao is None:
        messages.error(request, "Escolha uma integracao ativa para sincronizar.")
        return HttpResponseRedirect(voltar)
    if not ids:
        messages.warning(request, "Nenhum produto selecionado.")
        return HttpResponseRedirect(voltar)
    loja = configuracao.get_plataforma_display()
    itens = _permitidos(configuracao)
    recursos = [r for r in ("produtos", "estoque") if itens.get(r, {}).get("permitido")]
    try:
        execucao = sincronizacao.iniciar(configuracao, sincronizacao.EXPORTAR,
                                         recursos or ["produtos"], produtos=ids)
    except sincronizacao.SincronizacaoEmAndamento as andamento:
        messages.warning(request, format_html(
            'Ja existe uma sincronizacao de {} em andamento. <a href="{}">Acompanhe a '
            "tarefa</a> e tente de novo quando ela terminar.",
            loja, url_execucao(andamento.execucao)))
        return HttpResponseRedirect(voltar)
    except ValueError as erro:
        messages.error(request, str(erro))
        return HttpResponseRedirect(voltar)
    extra = "" if "estoque" in recursos else " (sem estoque: Enviar > Estoque esta desligado)"
    messages.success(request, f"Sincronizacao de {len(ids)} produto(s) com {loja} "
                              f"enviada para a fila{extra}.")
    return HttpResponseRedirect(url_execucao(execucao))


@admin.action(description="Sincronizar com integracao (envia dados e estoque)",
              permissions=["change"])
def sincronizar_com_integracao(modeladmin, request, queryset):
    ids = list(queryset.order_by("pk").values_list("pk", flat=True))
    return sincronizar(request, ids, request.POST.get("integracao", ""),
                       request.get_full_path())


class SincronizarProdutoMixin:
    """Rota do botao do produto e o contexto do dialog nas duas telas."""

    def get_urls(self):
        rota = path("<path:object_id>/sincronizar/",
                    self.admin_site.admin_view(self.sincronizar_view),
                    name="loja_produto_sincronizar")
        return [rota, *super().get_urls()]

    def sincronizar_view(self, request, object_id):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        produto = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.has_change_permission(request, produto):
            messages.error(request, "Sem permissao para alterar este produto.")
            return HttpResponseRedirect(reverse("admin:loja_produto_changelist"))
        voltar = reverse("admin:loja_produto_change", args=[produto.pk])
        return sincronizar(request, [produto.pk], request.POST.get("integracao", ""), voltar)

    def _contexto_dialog(self, extra_context):
        return {**(extra_context or {}), "integracoes_sincronizar": integracoes_do_dialog()}

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, self._contexto_dialog(extra_context))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(request, object_id, form_url,
                                   self._contexto_dialog(extra_context))
