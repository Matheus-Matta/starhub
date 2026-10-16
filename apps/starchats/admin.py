from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.core.admin_base import TemaModelAdmin
from apps.core.tarefas import enfileirar
from apps.core.tenant.context import get_current_account_id
from apps.starchats.forms import ConfiguracaoStarChatsForm
from apps.starchats.models import (
    ConfiguracaoStarChats,
    ConjuntoEnvio,
    EnvioStarChats,
    ModeloMensagem,
    RegraEnvio,
)


@admin.register(ConfiguracaoStarChats)
class ConfiguracaoStarChatsAdmin(TemaModelAdmin):
    form = ConfiguracaoStarChatsForm
    relatorio = False
    fieldsets = [
        ("Conexao", {"fields": [("url_base", "conta_externa_id"), "token_acesso"]}),
        ("Canal", {"fields": ["caixa_entrada_id", "active", "sincronizar_agora"]}),
        (
            "Ultima sincronizacao",
            {"fields": [("sincronizado_em", "caixa_entrada_nome"), "ultimo_erro"]},
        ),
    ]
    readonly_fields = ["sincronizado_em", "caixa_entrada_nome", "ultimo_erro"]

    def changelist_view(self, request, extra_context=None):
        configuracao = ConfiguracaoStarChats.all_objects.filter(
            account_id=get_current_account_id()
        ).first()
        destino = (
            reverse("admin:starchats_configuracaostarchats_change", args=[configuracao.pk])
            if configuracao
            else reverse("admin:starchats_configuracaostarchats_add")
        )
        return HttpResponseRedirect(destino)

    def has_add_permission(self, request):
        return not ConfiguracaoStarChats.all_objects.filter(
            account_id=get_current_account_id()
        ).exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        caixa_mudou = "caixa_entrada_id" in form.changed_data and obj.caixa_entrada_id
        if form.cleaned_data.get("sincronizar_agora") or caixa_mudou:
            from apps.starchats.tasks import sincronizar_starchats

            enfileirar(sincronizar_starchats, str(obj.account_id))
            messages.success(request, "Configuracao salva; caixas e modelos foram para a fila.")
        else:
            messages.success(request, "Configuracao do StarChats salva.")


@admin.register(ModeloMensagem)
class ModeloMensagemAdmin(TemaModelAdmin):
    list_display = ["nome", "idioma", "categoria", "situacao", "active"]
    list_filter = ["idioma", "categoria", "situacao", "active"]
    search_fields = ["nome", "conteudo"]
    readonly_fields = [
        "configuracao",
        "caixa_entrada_id",
        "identificador_externo",
        "nome",
        "idioma",
        "categoria",
        "situacao",
        "conteudo",
        "active",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RegraEnvio)
class RegraEnvioAdmin(TemaModelAdmin):
    list_display = ["nome", "campo", "operador", "valor", "active"]
    list_filter = ["campo", "operador", "active"]
    search_fields = ["nome", "valor"]
    fieldsets = [
        (
            "Condicao reutilizavel",
            {"fields": ["nome", ("campo", "operador"), "valor", "active"]},
        )
    ]


@admin.register(ConjuntoEnvio)
class ConjuntoEnvioAdmin(TemaModelAdmin):
    list_display = ["nome", "evento", "modo", "modelo", "active"]
    list_filter = ["evento", "modo", "active"]
    search_fields = ["nome", "modelo__nome"]
    fieldsets = [
        ("Quando enviar", {"fields": ["nome", ("evento", "modo"), "regras", "active"]}),
        (
            "Mensagem",
            {"fields": [
                "modelo",
                "parametros_corpo",
                "parametros_cabecalho",
                ("midia_cabecalho_url", "midia_cabecalho_tipo"),
                "codigo_botao",
                "enviar_uma_vez",
            ]},
        ),
    ]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "modelo":
            kwargs["queryset"] = ModeloMensagem.objects.filter(active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(EnvioStarChats)
class EnvioStarChatsAdmin(TemaModelAdmin):
    list_display = ["conjunto", "cliente", "evento", "status", "created_at"]
    list_filter = ["status", "evento", "conjunto"]
    search_fields = ["cliente__nome", "cliente__email", "conteudo", "mensagem_externa_id"]
    readonly_fields = [
        "conjunto",
        "cliente",
        "tipo_objeto",
        "objeto_id",
        "evento",
        "status",
        "conteudo",
        "mensagem_externa_id",
        "erro",
        "processando_em",
        "enviado_em",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
