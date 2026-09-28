"""Todo formulario do admin em portugues.

Campo sem verbose_name aparece com o nome do codigo: `compare_at_price` vira
"Compare at price" na tela. O teste abre o "Adicionar" de todo model registrado
e procura palavra em ingles nos rotulos e nos cabecalhos dos inlines.
"""

import re

import pytest
from django.contrib import admin
from django.urls import reverse

INGLES = re.compile(
    r"\b(price|type|policy|quantity|shipping|tracking|amount|currency|default|stock|"
    r"inventory|weight|barcode|usage|minimum|customer|product|eligibility|order|free|"
    r"scopes|enabled|priority|rules|channel|provider|installments|transaction|delivered|"
    r"shipped|created|updated|placed|paid|cancelled|fulfilled|source|number|external|"
    r"compare|sale|cost|taxable|downloadable|requires|sold|dimensions|stacking|value|"
    r"name|code|description|starts|ends|count|first|once|component|platform|entity|"
    r"desired|sync|payload|error|target|action|account|profile)\b",
    re.IGNORECASE,
)
ROTULOS = re.compile(r"<label[^>]*>(.*?)</label>|<th[^>]*>(.*?)</th>", re.DOTALL)


def _textos(html):
    for rotulo, cabecalho in ROTULOS.findall(html):
        texto = re.sub(r"<[^>]+>", " ", rotulo or cabecalho)
        texto = " ".join(texto.split())
        if texto:
            yield texto


def _telas_de_adicionar():
    for model in admin.site._registry:
        opts = model._meta
        if opts.app_label in ("core", "loja", "woo_api"):
            yield f"admin:{opts.app_label}_{opts.model_name}_add"


@pytest.mark.django_db
@pytest.mark.parametrize("rota", sorted(_telas_de_adicionar()))
def test_formulario_de_adicionar_nao_tem_rotulo_em_ingles(admin_logado, rota):
    resposta = admin_logado.get(reverse(rota))
    if resposta.status_code == 403:  # model sem "adicionar" (ex.: contas so por comando)
        pytest.skip("tela de adicionar bloqueada")
    assert resposta.status_code == 200
    em_ingles = [texto for texto in _textos(resposta.content.decode()) if INGLES.search(texto)]
    assert em_ingles == []
