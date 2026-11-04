from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.template.loader import render_to_string

from apps.core.admin_base import TemaModelAdmin
from apps.core.admin_lista_modal import url_popup
from apps.core.json_widgets import TagsTema
from apps.core.tarefas import enfileirar
from apps.starchats.models import ConjuntoEnvio, ModeloMensagem, RegraEnvio
from apps.starchats.telefones import NumeroInvalido, numero_whatsapp


class ConjuntoEnvioForm(forms.ModelForm):
    numero_teste = forms.CharField(
        label="Numero para o teste",
        required=False,
        help_text="WhatsApp com DDD. O envio usa valores de exemplo no modelo.",
        widget=forms.TextInput(attrs={"placeholder": "(11) 99999-9999"}),
    )
    enviar_teste = forms.BooleanField(
        label="Enviar mensagem de teste ao salvar",
        required=False,
    )

    class Meta:
        model = ConjuntoEnvio
        fields = [
            "account", "active", "origin", "metadados", "nome", "evento", "modo",
            "modelo", "limite_diario", "numeros_permitidos", "parametros_corpo",
            "parametros_cabecalho", "midia_cabecalho_url", "midia_cabecalho_tipo",
            "codigo_botao", "enviar_uma_vez",
        ]

    def clean(self):
        dados = super().clean()
        numero = dados.get("numero_teste")
        if dados.get("enviar_teste") and not numero:
            self.add_error("numero_teste", "Informe o numero que recebera o teste.")
        if numero:
            try:
                numero_whatsapp(numero)
            except NumeroInvalido as erro:
                self.add_error("numero_teste", str(erro))
        return dados


@admin.register(RegraEnvio)
class RegraEnvioAdmin(TemaModelAdmin):
    pai_da_lista = "conjunto"
    relatorio = False
    list_display = ["nome", "conjunto", "campo", "operador", "valor", "active"]
    list_filter = ["campo", "operador", "active"]
    search_fields = ["nome", "valor", "conjunto__nome"]
    fieldsets = [("Condicao", {
        "fields": ["conjunto", "nome", ("campo", "operador"), "valor", "active"],
    })]

    def has_module_permission(self, request):
        return False


@admin.register(ConjuntoEnvio)
class ConjuntoEnvioAdmin(TemaModelAdmin):
    form = ConjuntoEnvioForm
    list_display = ["nome", "evento", "modo", "modelo", "active"]
    list_filter = ["evento", "modo", "active"]
    search_fields = ["nome", "modelo__nome"]
    readonly_fields = ["lista_regras"]
    readonly_largos = ["lista_regras"]
    campos_json = {"numeros_permitidos": TagsTema(simples=True)}
    fieldsets = [
        ("Quando enviar", {"fields": ["nome", ("evento", "modo"), "active"]}),
        ("Regras", {
            "classes": ["secao-lista"],
            "fields": ["lista_regras"],
            "description": "Cadastre aqui as condicoes que liberam este conjunto.",
        }),
        ("Controle de envio", {"fields": [
            ("limite_diario", "enviar_uma_vez"), "numeros_permitidos",
        ]}),
        ("Mensagem", {"fields": [
            "modelo", "parametros_corpo", "parametros_cabecalho",
            ("midia_cabecalho_url", "midia_cabecalho_tipo"), "codigo_botao",
        ]}),
        ("Envio de teste", {"fields": [("numero_teste", "enviar_teste")]}),
    ]

    @admin.display(description="Regras")
    def lista_regras(self, obj):
        regras = list(obj.regras.all()) if obj.pk else []
        linhas = [{
            "regra": regra,
            "url_editar": url_popup("admin:starchats_regraenvio_change", regra.pk),
            "url_excluir": url_popup("admin:starchats_regraenvio_delete", regra.pk),
        } for regra in regras]
        return render_to_string("admin/starchats/lista_regras_envio.html", {
            "linhas": linhas,
            "url_adicionar": url_popup(
                "admin:starchats_regraenvio_add",
                conjunto=obj.pk,
                account=obj.account_id,
                nome=obj.nome,
            ) if obj.pk else None,
        })

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "modelo":
            kwargs["queryset"] = ModeloMensagem.objects.filter(active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if form.cleaned_data.get("enviar_teste"):
            from apps.starchats.tasks import enviar_teste_starchats

            argumentos = (
                str(obj.account_id), obj.pk, form.cleaned_data["numero_teste"],
            )
            transaction.on_commit(
                lambda: enfileirar(enviar_teste_starchats, *argumentos)
            )
            messages.success(request, "Mensagem de teste enviada para a fila.")
