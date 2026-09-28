"""Campos que so aparecem conforme outro (ModelAdmin.condicoes) e a validacao que
acompanha cada escolha. O mostrar/esconder em si e JS (static/starhub/js/condicoes.js)."""

import json
import re

import pytest
from django.contrib import admin
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import RequestFactory

from apps.core import admin_condicoes
from apps.core.models import User
from apps.loja.models import Cliente, Cupom, Produto


def test_regra_mal_escrita_estoura_em_vez_de_nao_fazer_nada():
    with pytest.raises(ImproperlyConfigured):
        admin_condicoes.validar({"cpf": {"campo": "tipo_documento", "igual": "cpf"}}, "X")
    with pytest.raises(ImproperlyConfigured):
        admin_condicoes.validar({"cpf": {"em": ["cpf"]}}, "X")


def _campos_do_form(form):
    # Data e hora viram dois inputs, mas o nome do campo e um so.
    return set(form.base_fields)


@pytest.mark.django_db
def test_toda_regra_aponta_para_campo_e_inline_que_existem(admin_logado):
    """Nome errado numa regra nao da erro nenhum na tela: o campo so nunca some."""
    request = RequestFactory().get("/admin/")
    request.user = User.objects.get(username="admin")
    problemas = []
    for model_admin in admin.site._registry.values():
        condicoes = getattr(model_admin, "condicoes", {})
        inlines = model_admin.get_inline_instances(request)
        prefixos = {f"{i.get_formset(request).get_default_prefix()}-group" for i in inlines}
        campos = _campos_do_form(model_admin.get_form(request))
        for alvo, regra in condicoes.items():
            if alvo.startswith("#") and alvo[1:] not in prefixos:
                problemas.append(f"{type(model_admin).__name__}: inline {alvo}")
            elif not alvo.startswith(("#", ".")) and alvo not in campos:
                problemas.append(f"{type(model_admin).__name__}: campo {alvo}")
            for item in admin_condicoes.regras(regra):
                if item["campo"] not in campos:
                    problemas.append(f"{type(model_admin).__name__}: controle {item['campo']}")
        for inline in inlines:
            campos_inline = _campos_do_form(inline.get_formset(request).form)
            for alvo, regra in getattr(inline, "condicoes", {}).items():
                controles = [item["campo"] for item in admin_condicoes.regras(regra)]
                nomes = [alvo, *controles]
                faltando = [n for n in nomes if n not in campos_inline]
                problemas += [f"{type(inline).__name__}: {n}" for n in faltando]
    assert problemas == []


@pytest.mark.django_db
def test_form_de_produto_leva_as_regras_para_a_tela(admin_logado):
    html = admin_logado.get("/admin/loja/produto/add/").content.decode()
    padrao = r'<script id="sh-condicoes" type="application/json">(.*?)</script>'
    bruto = re.search(padrao, html, re.S)
    regras = json.loads(bruto.group(1))
    assert regras["form"]["#componentes-group"] == {"campo": "tipo", "em": ["bundle"]}
    assert "bundle" not in regras["form"][".secao-variantes"]["em"]  # bundle sem variante
    assert "starhub/js/condicoes.js" in html
    variante = admin_logado.get("/admin/loja/varianteproduto/add/").content.decode()
    assert '"inventory_quantity": {"campo": "manage_inventory"' in variante


@pytest.mark.django_db
def test_tipo_de_documento_escolhido_torna_o_documento_obrigatorio():
    cliente = Cliente(email="a@b.test", tipo_documento="cnpj")
    with pytest.raises(ValidationError) as erro:
        cliente.full_clean(exclude=["account"])
    assert "cnpj" in erro.value.message_dict
    Cliente(email="b@b.test", tipo_documento="cnpj", cnpj="11222333000181").full_clean(
        exclude=["account"]
    )


@pytest.mark.django_db
def test_produto_externo_precisa_de_url():
    with pytest.raises(ValidationError) as erro:
        Produto(nome="Na outra loja", slug="x", tipo="external").full_clean(exclude=["account"])
    assert "url_externa" in erro.value.message_dict


@pytest.mark.django_db
def test_requisito_minimo_escolhido_pede_o_numero():
    cupom = Cupom(code="MIN", name="Minimo", discount_type="percentage", value=10,
                  minimum_requirement="subtotal")
    with pytest.raises(ValidationError) as erro:
        cupom.full_clean(exclude=["account"])
    assert "minimum_subtotal" in erro.value.message_dict


@pytest.mark.django_db
def test_elegibilidade_escolhida_pede_a_lista_no_admin(admin_logado, conta):
    resposta = admin_logado.post("/admin/loja/cupom/add/", {
        "account": conta.pk, "origin": "starhub", "code": "SO-ALGUNS", "name": "So alguns",
        "status": "draft", "currency": "BRL", "discount_type": "percentage", "value": "10",
        "stacking_policy": "deny", "minimum_requirement": "none",
        "customer_eligibility": "all", "product_eligibility": "specific_products",
        "once_per_order": "on",
    })
    assert resposta.status_code == 200
    assert "produtos" in resposta.context["adminform"].form.errors
    assert not Cupom.objects.exists()
