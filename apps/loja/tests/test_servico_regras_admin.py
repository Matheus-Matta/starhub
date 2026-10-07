"""Telas das regras do servico: lista na pagina do servico, form no modal."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.loja.models import Categoria, RegraServico, Servico
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db


@pytest.fixture
def montagem():
    return Servico.objects.create(nome="Montagem", preco=Decimal("120.00"))


@pytest.fixture
def sofa():
    produto = criar_produto("Sofa compacto", sku="SOF-1", price=Decimal("1500.00"))
    produto.categorias.add(Categoria.objects.create(nome="Sofas", slug="sofas"))
    return produto


def _add_url(servico):
    return reverse("admin:loja_regraservico_add") + f"?servico={servico.pk}&_popup=1"


def test_pagina_do_servico_lista_as_regras_com_o_add_em_modal(admin_logado, montagem, sofa):
    regra = RegraServico.objects.create(servico=montagem, ordem=10, preco=Decimal("90.00"))
    regra.categorias.set(sofa.categorias.all())

    html = admin_logado.get(
        reverse("admin:loja_servico_change", args=[montagem.pk])).content.decode()

    assert 'data-modal-chave="regras"' in html
    assert f"servico={montagem.pk}" in html and "_popup=1" in html
    linha = html.split('class="sh-linha-modal"')[1].split("</tr>")[0]
    assert "Sofas" in linha and "1 produto" in linha and "R$ 90,00" in linha


def test_form_do_modal_grava_a_regra_com_a_ordem_sugerida(admin_logado, montagem, sofa):
    RegraServico.objects.create(servico=montagem, ordem=10, preco_de=Decimal("1"))
    pagina = admin_logado.get(_add_url(montagem)).content.decode()
    assert 'name="ordem"' in pagina and 'value="20"' in pagina
    assert 'name="servico"' not in pagina or 'type="hidden" name="servico"' in pagina

    resposta = admin_logado.post(_add_url(montagem), {
        "servico": montagem.pk, "ordem": "20", "produtos": [sofa.pk], "active": "on",
        "preco": "150.00", "_popup": "1",
    })

    assert resposta.status_code == 200  # resposta do popup, que fecha o modal
    nova = RegraServico.objects.get(ordem=20)
    assert list(nova.produtos.all()) == [sofa] and nova.preco == Decimal("150.00")


def test_form_recusa_regra_sem_criterio_e_diz_o_que_fazer(admin_logado, montagem):
    resposta = admin_logado.post(_add_url(montagem), {
        "servico": montagem.pk, "ordem": "10", "active": "on", "_popup": "1"})

    assert "Escolha produtos, categorias ou uma faixa de preco" in resposta.content.decode()
    assert not RegraServico.objects.exists()


def test_pagina_do_produto_mostra_os_servicos_que_valem_para_ele(admin_logado, montagem, sofa):
    regra = RegraServico.objects.create(servico=montagem, ordem=10)
    regra.produtos.set([sofa])

    html = admin_logado.get(
        reverse("admin:loja_produto_change", args=[sofa.pk])).content.decode()

    secao = html.split('class="sh-servicos-do-produto"')[1].split("</table>")[0]
    assert "Montagem" in secao and "R$ 120,00" in secao


def test_regra_nao_aparece_sozinha_no_menu_nem_nos_relatorios(admin_logado):
    html = admin_logado.get(reverse("admin:index")).content.decode()
    menu = html.split('class="sidebar-menu"')[1].split("</nav>")[0]

    assert "/admin/loja/regraservico/" not in menu
    assert reverse("admin:relatorio", args=["loja.regraservico"]) not in menu
