from django.contrib import admin
from django.template.loader import render_to_string

from apps.core.admin_base import TemaModelAdmin
from apps.core.admin_utils import iniciais_de
from apps.core.filtros import FiltroPeriodo
from apps.loja.admin import campos
from apps.loja.admin.codigo_externo import CodigoExternoMixin
from apps.loja.admin.enderecos import EnderecosForm, secao_endereco
from apps.loja.models import Cliente
from apps.loja.services.clientes import endereco_do_cliente, gravar_endereco_do_cliente


class ClienteForm(EnderecosForm):
    class Meta:
        model = Cliente
        fields = "__all__"

    def endereco_inicial(self, tipo):
        return endereco_do_cliente(self.instance, tipo)


@admin.register(Cliente)
class ClienteAdmin(CodigoExternoMixin, TemaModelAdmin):
    entidade_externa = "clientes"
    form = ClienteForm
    campos_json = campos.CLIENTE
    list_display = [
        "cliente_info", "codigo_externo", "cidade", "telefone_fmt", "cliente_pagante", "created_at",
    ]
    list_display_links = ["cliente_info"]
    search_fields = ["email", "nome", "sobrenome", "usuario", "cpf", "cnpj"]
    list_filter = [("created_at", FiltroPeriodo), "cliente_pagante", "papel", "origin"]
    readonly_fields = ["created_at", "updated_at"]
    # Sem tipo escolhido (cliente que veio do ERP), os dois documentos aparecem.
    condicoes = {
        "cpf": {"campo": "tipo_documento", "em": ["cpf", ""]},
        "cnpj": {"campo": "tipo_documento", "em": ["cnpj", ""]},
        "empresa": {"campo": "tipo_documento", "em": ["cnpj", ""]},
    }
    fieldsets = [
        ("Cliente", {"fields": [
            ("nome", "sobrenome"), ("email", "usuario"), ("telefone", "papel"),
            ("tipo_documento", "empresa"), ("cpf", "cnpj"), ("nascimento", "locale"),
        ]}),
        secao_endereco("cobranca", "Endereco de cobranca"),
        secao_endereco("entrega", "Endereco de entrega"),
        ("Marketing", {"fields": [("aceita_marketing", "isento_imposto"), "notas"]}),
        ("Avancado", {"classes": ["collapse"], "fields": [
            "cliente_pagante", "avatar_url", "metadados", "active",
            ("created_at", "updated_at"),
        ]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("vinculos_endereco__endereco")

    @admin.display(description="cliente", ordering="nome")
    def cliente_info(self, obj):
        nome = obj.nome_completo or obj.email or f"Cliente {obj.pk}"
        return render_to_string("components/table_cliente.html", {
            "avatar_url": obj.avatar_url,
            "email": obj.email or "Sem e-mail",
            "iniciais": iniciais_de(nome),
            "nome": nome,
        })

    @admin.display(description="cidade")
    def cidade(self, obj):
        endereco = endereco_do_cliente(obj, "billing")
        partes = [endereco.city, endereco.state_code] if endereco else []
        return " / ".join(p for p in partes if p) or "-"

    @admin.display(description="telefone")
    def telefone_fmt(self, obj):
        endereco = endereco_do_cliente(obj, "billing")
        return obj.telefone or (endereco.phone if endereco else "") or "-"

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        for tipo, dados in form.enderecos_alterados():
            gravar_endereco_do_cliente(form.instance, tipo, dados, substituir=True)
