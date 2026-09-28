from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Value
from django.db.models.functions import Concat

from apps.loja.models import Cliente
from apps.loja.services.clientes import endereco_do_cliente, gravar_endereco_do_cliente
from apps.woo_api import datas, metadados
from apps.woo_api.erros import WooErro, parametro_invalido
from apps.woo_api.recursos import enderecos
from apps.woo_api.recursos.base import Recurso, texto


def erro_email_repetido():
    return WooErro(
        "registration-error-email-exists",
        "Ja existe uma conta com este e-mail. Busque o cliente por ?email= e atualize-o.",
        400,
    )


class ClienteRecurso(Recurso):
    modelo = Cliente
    nome = "customer"
    campo_busca = ("email", "nome", "sobrenome", "usuario")
    ordenacoes = {
        "id": "id", "include": "id", "name": "nome_ordem", "registered_date": "created_at",
    }
    ordenacao_padrao = ("name", "asc")
    suporta_lixeira = False

    def queryset(self):
        return Cliente.objects.annotate(
            nome_ordem=Concat("nome", Value(" "), "sobrenome")
        ).prefetch_related("vinculos_endereco__endereco")

    def filtrar(self, qs, params):
        if params.get("email"):
            qs = qs.filter(email_normalizado=params["email"].strip().casefold())
        papel = params.get("role") or "customer"
        if papel != "all":
            qs = qs.filter(papel=papel)
        return super().filtrar(qs, params)

    def para_woo(self, obj):
        return {
            "id": obj.pk,
            **datas.par("date_created", obj.created_at),
            **datas.par("date_modified", obj.updated_at),
            "email": obj.email,
            "first_name": obj.nome,
            "last_name": obj.sobrenome,
            "role": obj.papel,
            "username": obj.usuario,
            "billing": enderecos.saida(endereco_do_cliente(obj, "billing"), "billing"),
            "shipping": enderecos.saida(endereco_do_cliente(obj, "shipping"), "shipping"),
            "is_paying_customer": obj.cliente_pagante,
            "avatar_url": obj.avatar_url,
            "meta_data": obj.metadados or [],
        }

    def gravar(self, obj, dados, criando):
        if criando and not dados.get("email"):
            raise WooErro("rest_missing_callback_param", "Parametro(s) ausente(s): email", 400,
                          {"params": ["email"]})
        if "email" in dados:
            email = texto(dados["email"], "email", 254).strip().lower()
            try:
                validate_email(email)
            except ValidationError as erro:
                raise parametro_invalido("email", "E-mail invalido.") from erro
            repetido = Cliente.objects.filter(email_normalizado=email.casefold())
            if repetido.exclude(pk=obj.pk).exists():
                raise erro_email_repetido()
            obj.email = email
        for campo, atributo in (("first_name", "nome"), ("last_name", "sobrenome"),
                                ("username", "usuario"), ("role", "papel")):
            if campo in dados:
                setattr(obj, atributo, texto(dados[campo], campo, 150))
        if "meta_data" in dados:
            obj.metadados = metadados.mesclar(obj.metadados, dados["meta_data"])
        obj.save()
        for tipo in ("billing", "shipping"):
            recebido = enderecos.recebido(dados, tipo)
            if recebido is not None:
                enderecos.gravar(gravar_endereco_do_cliente, obj, tipo, recebido, tipo=tipo)
        if criando and (dados.get("date_created") or dados.get("date_created_gmt")):
            obj.created_at = datas.ler_do_corpo(dados, "date_created")
            # auto_now_add ignora o valor no save(); o update grava a data do ERP.
            Cliente.objects.filter(pk=obj.pk).update(created_at=obj.created_at)
        return obj

    def erro_integridade(self, erro):
        return erro_email_repetido()
