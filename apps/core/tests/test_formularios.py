"""Formularios do admin: placeholder, mascara, validadores e grade de colunas."""

import pytest
from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from apps.core import validators
from apps.core.json_widgets import JSONTema
from apps.core.models import User
from apps.core.widgets import DataHoraTema, DataTema
from apps.loja.models import Cliente, VarianteProduto
from apps.loja.services.variantes import criar_produto

ENTRADAS = (forms.TextInput, forms.Textarea, forms.NumberInput, forms.EmailInput, forms.URLInput)


@pytest.mark.parametrize(("validar", "bom", "ruim"), [
    (validators.validar_cpf, "529.982.247-25", "529.982.247-24"),
    (validators.validar_cnpj, "11.222.333/0001-81", "11.222.333/0001-80"),
    (validators.validar_documento, "11222333000181", "111.111.111-11"),
    (validators.validar_telefone, "(81) 99999-9999", "9999-999"),
    (validators.validar_telefone, "+1 415 555 2671", "(81) 9999"),
    (validators.validar_gtin, "7891234567895", "7891234567890"),
    (validators.validar_uf, "PE", "XX"),
])
def test_validadores_aceitam_o_certo_com_mascara_e_recusam_o_errado(validar, bom, ruim):
    validar(bom)
    with pytest.raises(ValidationError):
        validar(ruim)


@pytest.mark.django_db
def test_todo_campo_de_digitar_tem_placeholder(admin_logado):
    """Campo novo sem exemplo cai aqui: o padrao fica em apps/core/ui/entradas.py."""
    request = RequestFactory().get("/admin/")
    request.user = User.objects.get(username="admin")
    sem = []
    for model_admin in admin.site._registry.values():
        if model_admin.model._meta.app_label not in ("core", "loja", "woo_api"):
            continue  # admin de terceiro (auditlog): so leitura, fora do tema
        forms_ = [(model_admin.model, model_admin.get_form(request))]
        forms_ += [(i.model, i.get_formset(request).form)
                   for i in model_admin.get_inline_instances(request)]
        for model, form in forms_:
            for nome, campo in form.base_fields.items():
                widget = getattr(campo.widget, "widget", campo.widget)
                pular = isinstance(widget, (JSONTema, DataTema, DataHoraTema, forms.PasswordInput))
                digitavel = isinstance(widget, ENTRADAS) and not pular
                if digitavel and not widget.attrs.get("placeholder"):
                    sem.append(f"{model.__name__}.{nome}")
    assert sem == []


@pytest.mark.django_db
def test_cpf_e_cnpj_com_mascara_sao_gravados_so_com_digitos(admin_logado, conta):
    """Com a mascara "529.982.247-25" tem 14 caracteres e o campo so cabe 11."""
    resposta = admin_logado.post("/admin/loja/cliente/add/", {
        "account": conta.pk, "origin": "starhub", "email": "ana@cliente.test", "papel": "customer",
        "locale": "pt-BR", "cpf": "529.982.247-25", "cnpj": "11.222.333/0001-81",
        "telefone": "(81) 99999-9999", "metadados": "[]",
    })
    assert resposta.status_code == 302, resposta.content.decode()[:1500]
    cliente = Cliente.objects.get()
    assert (cliente.cpf, cliente.cnpj, cliente.telefone) == (
        "52998224725", "11222333000181", "81999999999",
    )


@pytest.mark.django_db
def test_documento_e_telefone_invalidos_voltam_como_erro_no_campo(admin_logado, conta):
    resposta = admin_logado.post("/admin/loja/cliente/add/", {
        "account": conta.pk, "origin": "starhub", "email": "ana@cliente.test", "papel": "customer",
        "locale": "pt-BR", "cnpj": "11.222.333/0001-80", "telefone": "(81) 9999",
        "metadados": "[]",
    })
    erros = resposta.context["adminform"].form.errors
    assert set(erros) == {"cnpj", "telefone"}


@pytest.mark.django_db
def test_endereco_brasileiro_valida_uf_e_cep_e_estrangeiro_passa(admin_logado, conta):
    base = {"account": conta.pk, "origin": "starhub", "active": "on", "metadados": "[]",
            "metadata": "{}"}
    resposta = admin_logado.post("/admin/core/address/add/", {
        **base, "country_code": "BR", "state_code": "XX", "postal_code": "5003",
    })
    assert set(resposta.context["adminform"].form.errors) == {"state_code", "postal_code"}
    resposta = admin_logado.post("/admin/core/address/add/", {
        **base, "country_code": "US", "state_code": "CA", "postal_code": "94105-1234",
    })
    assert resposta.status_code == 302


@pytest.mark.django_db
def test_campos_levam_placeholder_mascara_e_largura_na_tela(admin_logado):
    html = admin_logado.get("/admin/core/address/add/").content.decode()
    assert 'placeholder="00000-000"' in html and 'data-mascara="cep"' in html
    linha = html.split('class="form-row field-postal_code')[1].split('class="form-row')[0]
    # "CEP | Endereco | Numero" = 3 + 7 + 2 colunas na mesma linha.
    assert linha.count("celula-c3") == 1 and "celula-c7" in linha and "celula-c2" in linha


def test_promocao_maior_que_o_preco_e_recusada(db):
    variante = criar_produto("Caneca", price=10).variante_padrao
    variante.sale_price = 12
    with pytest.raises(ValidationError) as erro:
        variante.full_clean()
    assert "sale_price" in erro.value.message_dict
    variante.barcode = "7891234567890"
    with pytest.raises(ValidationError) as erro:
        VarianteProduto.full_clean(variante)
    assert "barcode" in erro.value.message_dict


@pytest.mark.django_db
def test_endereco_do_cliente_sao_campos_do_form_em_colunas(admin_logado):
    """Antes o endereco era um JSON desenhado pelo JS: sem JS, sem colunas e sem mascara."""
    html = admin_logado.get("/admin/loja/cliente/add/").content.decode()
    linha = html.split('class="form-row field-cobranca_postcode')[1].split('class="form-row')[0]
    assert "celula-c3" in linha and "celula-c7" in linha and "celula-c2" in linha
    assert 'name="cobranca_postcode"' in linha and 'data-mascara="cep"' in linha
    assert 'placeholder="00000-000"' in linha


@pytest.mark.django_db
def test_editar_endereco_no_admin_mantem_o_que_o_erp_mandou_a_mais(admin_logado, conta):
    from apps.loja.services.clientes import endereco_do_cliente, gravar_endereco_do_cliente

    cliente = Cliente.objects.create(email="ana@cliente.test")
    gravar_endereco_do_cliente(cliente, "billing", {"city": "Recife", "persontype": "F"})
    resposta = admin_logado.get(f"/admin/loja/cliente/{cliente.pk}/change/")
    dados = {k: v for k, v in resposta.context["adminform"].form.initial.items()}
    assert dados["cobranca_city"] == "Recife" and dados["cobranca_outros"] == {"persontype": "F"}
    admin_logado.post(f"/admin/loja/cliente/{cliente.pk}/change/", {
        "email": "ana@cliente.test", "papel": "customer", "locale": "pt-BR", "metadados": "[]",
        "cobranca_city": "Olinda", "cobranca_state": "pe", "cobranca_country": "BR",
        "cobranca_postcode": "53020-000", "cobranca_outros": '{"persontype": "F"}',
    })
    endereco = endereco_do_cliente(Cliente.objects.get(), "billing")
    assert (endereco.city, endereco.state_code) == ("Olinda", "PE")
    assert endereco.postal_code == "53020000"
    assert endereco.metadata["persontype"] == "F"


@pytest.mark.django_db
def test_endereco_com_cep_invalido_volta_erro_no_campo_do_cep(admin_logado, conta):
    resposta = admin_logado.post("/admin/loja/cliente/add/", {
        "account": conta.pk, "origin": "starhub", "email": "ana@cliente.test",
        "papel": "customer", "locale": "pt-BR", "metadados": "[]",
        "cobranca_country": "BR", "cobranca_postcode": "5003", "cobranca_cpf": "111.111.111-11",
    })
    erros = resposta.context["adminform"].form.errors
    assert {"cobranca_postcode", "cobranca_cpf"} <= set(erros)
