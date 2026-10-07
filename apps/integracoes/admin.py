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
from apps.integracoes import admin_frete, permissoes
from apps.integracoes.admin_sincronizacao import (
    listas_do_modal,
    processar_sincronizacao,
)
from apps.integracoes.forms import ConfiguracaoShopifyForm
from apps.integracoes.forms_suri import ConfiguracaoSuriForm
from apps.integracoes.forms_woocommerce import ConfiguracaoWooCommerceForm
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.shopify.frete_checklist import checklist
from apps.shopify.tasks import (
    cadastrar_frete_shopify,
    cadastrar_webhooks_shopify,
    verificar_frete_shopify,
)
from apps.suri.tasks import cadastrar_webhooks_suri
from apps.woocommerce.tasks import cadastrar_webhooks_woocommerce

# Botoes de acao da tela da Shopify: acao do POST -> (tipo da tarefa, shared_task).
ACOES = {
    "webhooks": (ExecucaoIntegracao.Tipo.WEBHOOKS, cadastrar_webhooks_shopify),
    "frete": (ExecucaoIntegracao.Tipo.FRETE_CHECKOUT, cadastrar_frete_shopify),
    "verificar_frete": (ExecucaoIntegracao.Tipo.VERIFICAR_FRETE, verificar_frete_shopify),
}
Plataforma = ConfiguracaoIntegracao.Plataforma
CAMPOS_API = ("dominio_loja", "token_acesso", "segredo_app", "segredo_avaliacoes",
              "url_webhook", "id_vendedor", "active")
# O que muda de uma plataforma para outra na mesma tela de configuracao.
TELAS = {
    Plataforma.SHOPIFY: {"nome": "Shopify", "form": ConfiguracaoShopifyForm, "acoes": ACOES},
    Plataforma.WOOCOMMERCE: {
        "nome": "WooCommerce", "form": ConfiguracaoWooCommerceForm,
        "acoes": {"webhooks": (ExecucaoIntegracao.Tipo.WEBHOOKS,
                               cadastrar_webhooks_woocommerce)},
    },
    Plataforma.SURI: {
        "nome": "Suri Shop", "form": ConfiguracaoSuriForm,
        "acoes": {"webhooks": (ExecucaoIntegracao.Tipo.WEBHOOKS, cadastrar_webhooks_suri)},
    },
}


@admin.register(ConfiguracaoIntegracao)
class ConfiguracaoIntegracaoAdmin(TemaModelAdmin):
    exclude = [
        "permissoes", "token_criptografado", "segredo_criptografado",
        "segredo_avaliacoes_criptografado",
    ]
    relatorio = False  # a lista redireciona para a tela de cada plataforma

    def get_urls(self):
        urls = [
            path(
                "shopify/",
                self.admin_site.admin_view(self.shopify_view),
                name="integracoes_configuracaointegracao_shopify",
            ),
            path(
                "woocommerce/",
                self.admin_site.admin_view(self.woocommerce_view),
                name="integracoes_configuracaointegracao_woocommerce",
            ),
            path(
                "suri/",
                self.admin_site.admin_view(self.suri_view),
                name="integracoes_configuracaointegracao_suri",
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
        return self._configuracao_view(request, Plataforma.SHOPIFY)

    def woocommerce_view(self, request):
        return self._configuracao_view(request, Plataforma.WOOCOMMERCE)

    def suri_view(self, request):
        return self._configuracao_view(request, Plataforma.SURI)

    def _configuracao_view(self, request, plataforma):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        pode_editar = self.has_change_permission(request)
        if request.method == "POST" and not pode_editar:
            raise PermissionDenied
        tela = TELAS[plataforma]
        conta_id = get_current_account_id()
        configuracao = ConfiguracaoIntegracao.all_objects.filter(
            account_id=conta_id, plataforma=plataforma
        ).first()
        instancia = configuracao or ConfiguracaoIntegracao(
            account_id=conta_id, plataforma=plataforma
        )
        url_webhook = instancia.url_webhook or request.build_absolute_uri(
            f"/integracoes/{plataforma}/webhook"
        )
        if request.method == "POST" and request.POST.get("acao") == "sincronizar":
            # O modal e um form proprio (sem os campos da conexao): nao passa pelo form abaixo.
            return processar_sincronizacao(request, configuracao, request.path)
        form = tela["form"](
            request.POST or None,
            instance=instancia,
            initial={"url_webhook": url_webhook},
        )
        if configuracao and plataforma == Plataforma.SHOPIFY:
            # O tema precisa deste endereco (com o id da loja). Pela URL publica dos
            # webhooks: o admin aberto em localhost daria um endereco que a loja nao alcanca.
            caminho = reverse("shopify_avaliacoes", args=[configuracao.pk])
            url = urljoin(configuracao.url_webhook or request.build_absolute_uri("/"), caminho)
            form.fields["segredo_avaliacoes"].help_text += f" Endereco para o tema: {url}"
        if not request.user.is_superuser:
            # Fora do form, o valor salvo fica como esta (o construct_instance ignora).
            form.fields.pop("encaminhar_pedidos", None)
        if not pode_editar:
            for campo in form.fields.values():
                campo.disabled = True
        if request.method == "POST" and form.is_valid():
            configuracao = form.save(commit=False)
            configuracao.account_id = conta_id
            configuracao.plataforma = plataforma
            configuracao.nome = tela["nome"]
            configuracao.versao_api = ConfiguracaoIntegracao.VERSAO_API_FIXA
            configuracao.save()
            acao = request.POST.get("acao", "salvar")
            if acao in ("frete_ativar", "frete_desativar") and plataforma == Plataforma.SHOPIFY:
                self._ligar_frete(request, configuracao, acao == "frete_ativar")
            elif acao in ("frete_ligar", "frete_desligar") and admin_frete.contexto(
                    plataforma, configuracao) is not None:
                admin_frete.ligar(request, plataforma, configuracao, acao == "frete_ligar")
            elif acao in tela["acoes"]:
                self._enfileirar(request, configuracao, *tela["acoes"][acao])
            else:
                messages.success(request, f"Configuracao do {tela['nome']} salva.")
            return HttpResponseRedirect(request.path)
        contexto = {
            **self.admin_site.each_context(request),
            "title": f"Integracao {tela['nome']}",
            "subtitle": "Credenciais, fluxo de dados e acoes da loja.",
            "opts": self.model._meta,
            "form": form,
            "plataforma_nome": tela["nome"],
            "campos_api": [form[nome] for nome in CAMPOS_API if nome in form.fields],
            "campo_encaminhar": form["encaminhar_pedidos"]
            if "encaminhar_pedidos" in form.fields else None,
            "matriz": form.matriz_tela(),
            "operacoes": [rotulo for _, rotulo in permissoes.OPERACOES],
            "configuracao": configuracao,
            "frete": checklist(configuracao) if plataforma == Plataforma.SHOPIFY else None,
            "frete_loja": admin_frete.contexto(plataforma, configuracao),
            "pode_editar": pode_editar,
            "sincronizacao": listas_do_modal(configuracao),
            "url_tarefas": reverse("admin:integracoes_execucaointegracao_changelist"),
        }
        return TemplateResponse(request, "admin/integracoes/configuracao.html", contexto)

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
