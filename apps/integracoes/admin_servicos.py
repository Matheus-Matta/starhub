"""Botoes "Importar da Shopify" e "Exportar para a Shopify" na lista de Servicos.

Cada botao cria uma tarefa (ExecucaoIntegracao) e abre a tela dela, com barra,
falhas por servico e Retomar: a chamada a Shopify nunca roda dentro da requisicao.
POST com CSRF, porque os dois mudam dados (no hub ou na loja).
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.urls import path, reverse

from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.integracoes.retomar import colocar_na_fila

Tipo = ExecucaoIntegracao.Tipo
ACOES = {
    "importar": (Tipo.IMPORTAR_SERVICOS, "apps.shopify.tasks.importar_servicos_shopify"),
    "exportar": (Tipo.EXPORTAR_SERVICOS, "apps.shopify.tasks.exportar_servicos_shopify"),
}


class ServicosShopifyMixin:
    change_list_template = "admin/loja/servico/change_list.html"

    def get_urls(self):
        rota = f"{self.model._meta.app_label}_{self.model._meta.model_name}_shopify"
        return [
            path("shopify/<str:acao>/", self.admin_site.admin_view(self.shopify_view),
                 name=rota),
            *super().get_urls(),
        ]

    def changelist_view(self, request, extra_context=None):
        extra = {**(extra_context or {}), "pode_servicos_shopify":
                 self.has_change_permission(request), "urls_servicos_shopify": {
                     acao: reverse("admin:loja_servico_shopify", args=[acao]) for acao in ACOES}}
        return super().changelist_view(request, extra)

    def shopify_view(self, request, acao):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if acao not in ACOES or not self.has_change_permission(request):
            raise PermissionDenied
        tipo, tarefa = ACOES[acao]
        configuracao = ConfiguracaoIntegracao.objects.filter(
            plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY, active=True).first()
        lista = reverse("admin:loja_servico_changelist")
        if configuracao is None:
            messages.error(request, "Nenhuma loja Shopify ativa nesta conta: configure em "
                                    "Integracoes > Shopify e salve.")
            return HttpResponseRedirect(lista)
        if acao == "exportar" and not configuracao.enviar_servicos:
            messages.error(request, "Ligue \"enviar servicos\" em Integracoes > Shopify > "
                                    "Servicos e salve antes de exportar.")
            return HttpResponseRedirect(lista)
        execucao = ExecucaoIntegracao.objects.create(
            configuracao=configuracao, tipo=tipo, etapa="Na fila")
        transaction.on_commit(lambda: colocar_na_fila(execucao.pk, tarefa, (str(execucao.pk),)))
        messages.success(request, f"{execucao.get_tipo_display()} enviada para a fila.")
        return HttpResponseRedirect(
            reverse("admin:integracoes_execucaointegracao_change", args=[execucao.pk]))
