"""Administracao do nucleo multi-tenant.

Group nao e exposto: permissoes sao ligadas a AccessProfile pelo sistema.
User e Account nao herdam BaseModel (nao tem manager por conta); por isso o
filtro pela conta ativa e feito aqui. O superusuario ve todas as contas no admin
(ver apps/core/admin_conta.py).
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group

from apps.core.admin_base import TemaMixin
from apps.core.admin_logs import LogEntry, LogsAdmin
from apps.core.models import (
    AccessProfile,
    Account,
    Address,
    User,
)
from apps.core.tenant.context import get_current_account_id

if admin.site.is_registered(User):
    admin.site.unregister(User)
if admin.site.is_registered(Group):
    admin.site.unregister(Group)


# Logs do auditlog com o filtro por registro e separados por conta (admin_logs).
admin.site.unregister(LogEntry)
admin.site.register(LogEntry, LogsAdmin)


@admin.register(User)
class UsuarioAdmin(TemaMixin, UserAdmin):
    filter_horizontal = ()
    list_display = ["username", "email", "access_profile", "is_active", "is_staff"]
    list_filter = ["is_active", "access_profile"]
    fieldsets = [
        (None, {"fields": ["username", "password"]}),
        ("Dados pessoais", {"fields": [("first_name", "last_name"), "email"]}),
        ("Acesso", {"fields": ["account", "access_profile", "is_active", "is_staff"]}),
        ("Datas", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": [
            "username", "email", "access_profile", "password1", "password2", "is_staff",
        ]}),
    ]

    def get_fieldsets(self, request, obj=None):
        secoes = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return secoes
        return [
            (titulo, {**opcoes, "fields": [campo for campo in opcoes["fields"]
                                         if campo != "is_staff"]})
            for titulo, opcoes in secoes
        ]

    def get_list_display(self, request):
        colunas = super().get_list_display(request)
        return colunas if request.user.is_superuser else [
            coluna for coluna in colunas if coluna != "is_staff"
        ]

    def get_changeform_initial_data(self, request):
        inicial = super().get_changeform_initial_data(request)
        if request.user.is_superuser:
            inicial.setdefault("is_staff", True)
        return inicial

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(account_id=get_current_account_id())

    def save_model(self, request, obj, form, change):
        if not change and not obj.account_id:
            # Usuario comum nao ve o campo conta: o novo usuario entra na conta dele.
            obj.account_id = get_current_account_id()
        # Cadastro feito por gestor entra no admin; so o superusuario pode depois
        # desativar esse acesso sem que outra edicao volte a ativa-lo.
        if not change and not request.user.is_superuser:
            obj.is_staff = True
        super().save_model(request, obj, form, change)


@admin.register(Account)
class AccountAdmin(TemaMixin, admin.ModelAdmin):
    campos_editaveis_pela_conta = {"email", "phone", "dominio_avaliacoes"}
    list_display = ["name", "slug", "email", "currency", "active", "updated_at"]
    search_fields = ["name", "slug", "legal_name", "document", "email"]
    list_filter = ["active", "currency"]
    prepopulated_fields = {"slug": ["name"]}
    larguras = {"timezone": 5, "currency": 3}
    fieldsets = [
        ("Conta", {"fields": [("name", "slug"), ("legal_name", "document"), "active"]}),
        ("Contato", {"fields": [("email", "phone"), "dominio_avaliacoes"]}),
        ("Regiao", {"fields": [("timezone", "currency")]}),
    ]

    def get_queryset(self, request):
        # Cadastro de contas e fluxo administrativo explicito do superusuario; os
        # demais so enxergam a propria. Dados de negocio continuam isolados.
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(pk=get_current_account_id())

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return super().get_readonly_fields(request, obj)
        # Identidade, situacao e regiao da conta afetam todo o tenant. O administrador
        # da loja pode manter apenas os dados operacionais de contato e dominio.
        return [
            campo.name for campo in self.model._meta.fields
            if campo.editable and campo.name not in self.campos_editaveis_pela_conta
        ]

    def get_prepopulated_fields(self, request, obj=None):
        # O slug nao faz parte do formulario restrito e nao pode ser dependencia JS.
        return super().get_prepopulated_fields(request, obj) if request.user.is_superuser else {}

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AccessProfile)
class AccessProfileAdmin(TemaMixin, admin.ModelAdmin):
    list_display = ["name", "code", "group", "active", "is_system"]
    search_fields = ["name", "code"]
    list_filter = ["active", "is_system"]

    def get_readonly_fields(self, request, obj=None):
        # Group e estrutura interna: so o superusuario liga perfil a grupo. Perfil do
        # sistema (apps/core/perfis_padrao.py) nao muda de codigo nem de grupo.
        campos = list(super().get_readonly_fields(request, obj))
        travados = [] if request.user.is_superuser else ["group", "is_system"]
        if obj is not None and obj.is_system:
            travados = ["code", "group", "is_system"]
        return campos + [campo for campo in travados if campo not in campos]

    def has_delete_permission(self, request, obj=None):
        # Perfil do sistema: a conta sempre tem os iniciais (desative, se nao usar).
        if obj is not None and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Address)
class AddressAdmin(TemaMixin, admin.ModelAdmin):
    list_display = ["__str__", "recipient_name", "city", "state_code", "postal_code"]
    search_fields = ["name", "recipient_name", "address_line_1", "city", "postal_code"]
    # "CEP | Endereco | Numero" = 3 + 7 + 2 colunas (de 12).
    larguras = {
        "address_line_1": 7, "complement": 4, "address_line_2": 8, "neighborhood": 5,
        "city": 5, "state": 5, "country": 5, "reference": 12,
    }
    fieldsets = [
        ("Destinatario", {"fields": [
            ("name", "recipient_name"), ("company", "document"), ("phone", "email"),
        ]}),
        ("Endereco", {"fields": [
            ("postal_code", "address_line_1", "number"), ("complement", "address_line_2"),
            ("neighborhood", "city", "state_code"), ("state", "country", "country_code"),
            "reference",
        ]}),
        ("Localizacao", {"fields": [("latitude", "longitude"), "is_default"]}),
        ("Avancado", {"classes": ["collapse"], "fields": ["metadata", "metadados", "active"]}),
    ]
