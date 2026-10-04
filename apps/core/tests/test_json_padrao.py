"""Todo campo JSON do admin com widget do tema, e o valor gravado com o tipo certo."""

import json

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from apps.core import json_normalizar
from apps.core.json_regras import RegrasTema
from apps.core.json_widgets import JSONTema
from apps.core.services.rules import matches_rules
from apps.woo_api.models import ChaveApi


def test_objeto_mantem_numero_booleano_e_objeto_aninhado_dos_extras():
    """Antes tudo virava texto: {"limite": 10} voltava "10" e objeto quebrava."""
    saida = json_normalizar.objeto(
        {"limite": 10, "ativo": False, "loja": {"id": 1}, "nome": " Loja ", "vazio": ""}, []
    )
    assert saida == {"limite": 10, "ativo": False, "loja": {"id": 1}, "nome": "Loja"}


def test_valor_livre_vira_o_tipo_que_representa():
    assert [json_normalizar.valor_livre(v) for v in ("10", "true", '["a"]', "shopify", '"10"')] == [
        10, True, ["a"], "shopify", "10",
    ]


def test_regras_na_tela_viram_o_formato_do_motor_de_regras():
    widget = RegrasTema()
    regras = {"all": [{"field": "tags", "operator": "contains", "value": "shopify"}]}
    linhas = json.loads(widget.format_value(json.dumps(regras)))
    assert linhas == [{"grupo": "all", "field": "tags", "operator": "contains", "value": "shopify"}]
    enviado = [*linhas, {"grupo": "all", "field": "estoque", "operator": "gt", "value": "0"}]
    salvo = widget.normalizar(enviado, "Regras")
    assert salvo["all"][1] == {"field": "estoque", "operator": "gt", "value": 0}
    assert matches_rules({"tags": ["shopify"], "estoque": 3}, salvo)


@pytest.mark.parametrize("linha", [
    {"grupo": "all", "field": "tags", "operator": "exec", "value": ""},
    {"grupo": "all", "field": "", "operator": "eq", "value": "x"},
    {"grupo": "todas", "field": "tags", "operator": "eq", "value": "x"},
])
def test_regra_invalida_e_recusada(linha):
    """Operador fora da lista nunca chega ao motor: nada de codigo vindo do banco."""
    with pytest.raises(ValidationError):
        RegrasTema().normalizar([linha], "Regras")


@pytest.mark.django_db
def test_nenhum_campo_json_do_admin_aparece_cru(admin_logado, conta):
    """JSON cru na tela e proibido (AGENTS.md): campo novo sem widget cai aqui."""
    from apps.core.models import User

    request = RequestFactory().get("/admin/")
    request.user = User.objects.get(username="admin")
    crus = []
    for model_admin in admin.site._registry.values():
        forms = [(model_admin.model, model_admin.get_form(request))]
        forms += [(inline.model, inline.get_formset(request).form)
                  for inline in model_admin.get_inline_instances(request)]
        for model, form in forms:
            for nome, campo in form.base_fields.items():
                json_puro = campo.__class__.__name__ in ("JSONField", "CampoJSON")
                if json_puro and not isinstance(campo.widget, JSONTema):
                    crus.append(f"{model.__name__}.{nome}")
    assert crus == []


@pytest.mark.django_db
def test_admin_grava_escopos_da_chave_como_lista_de_textos(admin_logado, conta):
    resposta = admin_logado.post("/admin/woo_api/chaveapi/add/", {
        "account": conta.pk, "origin": "starhub", "descricao": "ERP", "permissao": "read",
        "active": "on",
        "scopes": json.dumps(["read", {"name": "write"}, "READ"]),
    })
    assert resposta.status_code == 302, resposta.content.decode()[:1500]
    assert ChaveApi.objects.get().scopes == ["read", "write"]
