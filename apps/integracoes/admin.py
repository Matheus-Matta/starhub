from urllib.parse import urljoin

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from apps.core.admin_base import TemaModelAdmin
from apps.core.models import ExternalReference
from apps.core.tarefas import enfileirar
from apps.core.tenant.context import get_current_account_id
from apps.integracoes import permissoes
from apps.integracoes.admin_sincronizacao import (
    listas_do_modal,
    processar_sincronizacao,
)
from apps.integracoes.forms import ConfiguracaoShopifyForm
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.shopify.frete_checklist import checklist
from apps.shopify.tasks import (
    cadastrar_frete_shopify,
    cadastrar_webhooks_shopify,
    verificar_frete_shopify,
)

# Botoes de acao da tela da Shopify: acao do POST -> (tipo da tarefa, shared_task).
ACOES = {
    "webhooks": (ExecucaoIntegracao.Tipo.WEBHOOKS, cadastrar_webhooks_shopify),
    "frete": (ExecucaoIntegracao.Tipo.FRETE_CHECKOUT, cadastrar_frete_shopify),
    "verificar_frete": (ExecucaoIntegracao.Tipo.VERIFICAR_FRETE, verificar_frete_shopify),
}


@admin.register(ConfiguracaoIntegracao)
class ConfiguracaoIntegracaoAdmin(TemaModelAdmin):
    exclude = [
        "permissoes", "token_criptografado", "segredo_criptografado",
        "segredo_avaliacoes_criptografado",
    ]

    def get_urls(self):
        urls = [
            path(
                "shopify/",
                self.admin_site.admin_view(self.shopify_view),
                name="integracoes_configuracaointegracao_shopify",
            ),
        ]
        return [*urls, *super().get_urls()]

    def changelist_view(self, request, extra_context=None):
        return HttpResponseRedirect(reverse("admin:integracoes_configuracaointegracao_shopify"))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def shopify_view(self, request):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        pode_editar = self.has_change_permission(request)
        if request.method == "POST" and not pode_editar:
            raise PermissionDenied
        conta_id = get_current_account_id()
        configuracao = ConfiguracaoIntegracao.all_objects.filter(
            account_id=conta_id, plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY
        ).first()
        instancia = configuracao or ConfiguracaoIntegracao(
            account_id=conta_id, plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY
        )
        url_webhook = instancia.url_webhook or request.build_absolute_uri(
            "/integracoes/shopify/webhook"
        )
        if request.method == "POST" and request.POST.get("acao") == "sincronizar":
            # O modal e um form proprio (sem os campos da conexao): nao passa pelo form abaixo.
            return processar_sincronizacao(request, configuracao, request.path)
        form = ConfiguracaoShopifyForm(
            request.POST or None,
            instance=instancia,
            initial={"url_webhook": url_webhook},
        )
        if configuracao:
            # O tema precisa deste endereco (com o id da loja). Pela URL publica dos
            # webhooks: o admin aberto em localhost daria um endereco que a loja nao alcanca.
            caminho = reverse("shopify_avaliacoes", args=[configuracao.pk])
            url = urljoin(configuracao.url_webhook or request.build_absolute_uri("/"), caminho)
            form.fields["segredo_avaliacoes"].help_text += f" Endereco para o tema: {url}"
        if not pode_editar:
            for campo in form.fields.values():
                campo.disabled = True
        if request.method == "POST" and form.is_valid():
            configuracao = form.save(commit=False)
            configuracao.account_id = conta_id
            configuracao.plataforma = ConfiguracaoIntegracao.Plataforma.SHOPIFY
            configuracao.nome = ConfiguracaoIntegracao.NOME_FIXO
            configuracao.versao_api = ConfiguracaoIntegracao.VERSAO_API_FIXA
            configuracao.save()
            acao = request.POST.get("acao", "salvar")
            if acao in ("frete_ativar", "frete_desativar"):
                self._ligar_frete(request, configuracao, acao == "frete_ativar")
            elif acao in ACOES:
                self._enfileirar(request, configuracao, *ACOES[acao])
            else:
                messages.success(request, "Configuracao do Shopify salva.")
            return HttpResponseRedirect(request.path)
        contexto = {
            **self.admin_site.each_context(request),
            "title": "Integracao Shopify",
            "subtitle": "Credenciais, fluxo de dados e acoes da loja.",
            "opts": self.model._meta,
            "form": form,
            "matriz": form.matriz_tela(),
            "operacoes": [rotulo for _, rotulo in permissoes.OPERACOES],
            "configuracao": configuracao,
            "frete": checklist(configuracao),
            "pode_editar": pode_editar,
            "sincronizacao": listas_do_modal(configuracao),
            "url_tarefas": reverse("admin:integracoes_execucaointegracao_changelist"),
        }
        return TemplateResponse(request, "admin/integracoes/shopify.html", contexto)

    def _ligar_frete(self, request, configuracao, ligar):
        configuracao.frete_ativo = ligar
        configuracao.save(update_fields=["frete_ativo", "updated_at"])
        cadastrado = ExternalReference.objects.filter(
            platform="shopify", entity_type="carrier_service",
            object_id=str(configuracao.pk)).exists()
        # Desligar o que nunca foi cadastrado nao precisa da Shopify; o resto atualiza la.
        if ligar or cadastrado:
            self._enfileirar(request, configuracao, *ACOES["frete"])
        estado = "ligado" if ligar else "desligado"
        messages.success(request, f"Frete do hub no checkout {estado}.")

    def _enfileirar(self, request, configuracao, tipo, tarefa):
        execucao = ExecucaoIntegracao.objects.create(configuracao=configuracao, tipo=tipo)
        resultado = enfileirar(tarefa, str(execucao.pk))
        ExecucaoIntegracao.objects.filter(pk=execucao.pk).update(celery_task_id=resultado.id)
        messages.success(request, f"{execucao.get_tipo_display()} foi enviada para a fila.")


# O admin das tarefas mora em admin_tarefas.py; importado aqui para o Django registrar.
from apps.integracoes import admin_tarefas  # noqa: E402, F401
