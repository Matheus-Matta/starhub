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
        ("Acesso", {"fields": ["account", "access_profile", ("is_active", "is_staff")]}),
        ("Datas", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {"classes": ["wide"], "fields": [
            "username", "email", "access_profile", "password1", "password2",
        ]}),
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(account_id=get_current_account_id())

    def save_model(self, request, obj, form, change):
        if not change and not obj.account_id:
            # Usuario comum nao ve o campo conta: o novo usuario entra na conta dele.
            obj.account_id = get_current_account_id()
        super().save_model(request, obj, form, change)


@admin.register(Account)
class AccountAdmin(TemaMixin, admin.ModelAdmin):
    list_display = ["name", "slug", "email", "currency", "active", "updated_at"]
    search_fields = ["name", "slug", "legal_name", "document", "email"]
    list_filter = ["active", "currency"]
    prepopulated_fields = {"slug": ["name"]}
    larguras = {"timezone": 5, "currency": 3}
    fieldsets = [
        ("Conta", {"fields": [("name", "slug"), ("legal_name", "document"), "active"]}),
        ("Contato", {"fields": [("email", "phone")]}),
        ("Regiao", {"fields": [("timezone", "currency")]}),
    ]

    def get_queryset(self, request):
        # Cadastro de contas e fluxo administrativo explicito do superusuario; os
        # demais so enxergam a propria. Dados de negocio continuam isolados.
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(pk=get_current_account_id())

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
