"""Regras cadastradas como filhas na pagina do conjunto de envio."""

import pytest
from django.urls import reverse

from apps.starchats.models import ConjuntoEnvio, RegraEnvio
from apps.starchats.tests.test_integracao import _configuracao, _modelo

pytestmark = pytest.mark.django_db


def _conjunto(conta):
    configuracao = _configuracao(conta)
    return ConjuntoEnvio.objects.create(
        account=conta,
        nome="Clientes pagantes",
        evento="cliente.criado",
        modelo=_modelo(conta, configuracao),
    )


def test_conjunto_lista_regras_e_abre_cadastro_no_modal(admin_logado, conta):
    conjunto = _conjunto(conta)
    regra = RegraEnvio.objects.create(
        account=conta,
        conjunto=conjunto,
        nome="Ja comprou",
        campo="cliente.cliente_pagante",
        operador="eq",
        valor="true",
    )

    html = admin_logado.get(
        reverse("admin:starchats_conjuntoenvio_change", args=[conjunto.pk])
    ).content.decode()

    assert 'data-modal-chave="regras"' in html
    assert f"conjunto={conjunto.pk}" in html and "_popup=1" in html
    assert "nome=Clientes+pagantes" in html
    linha = html.split('class="sh-linha-modal"')[1].split("</tr>")[0]
    assert regra.nome in linha and "Cliente: ja pagou" in linha and "igual a" in linha


def test_modal_grava_regra_no_conjunto_sem_mostrar_cadastro_separado(
    admin_logado, conta
):
    conjunto = _conjunto(conta)
    url = reverse("admin:starchats_regraenvio_add") + (
        f"?conjunto={conjunto.pk}&_popup=1"
    )

    pagina = admin_logado.get(url).content.decode()
    resposta = admin_logado.post(
        url,
        {
            "conjunto": conjunto.pk,
            "nome": "Telefone preenchido",
            "campo": "cliente.telefone",
            "operador": "is_not_null",
            "valor": "",
            "active": "on",
            "_popup": "1",
        },
    )

    assert 'name="conjunto"' not in pagina or 'type="hidden" name="conjunto"' in pagina
    assert resposta.status_code == 200
    assert RegraEnvio.objects.get().conjunto == conjunto
    pagina_inicial = admin_logado.get(reverse("admin:index")).content.decode()
    menu = pagina_inicial.split('class="sidebar-menu"')[1].split("</nav>")[0]
    assert "/admin/starchats/regraenvio/" not in menu


def test_nova_regra_aberta_pelo_conjunto_ja_traz_o_nome(admin_logado, conta):
    conjunto = _conjunto(conta)
    url = reverse("admin:starchats_regraenvio_add") + (
        f"?conjunto={conjunto.pk}&nome=Clientes+pagantes&_popup=1"
    )

    pagina = admin_logado.get(url).content.decode()

    assert 'name="nome" value="Clientes pagantes"' in pagina


def test_controles_do_conjunto_usam_lista_de_etiquetas(admin_logado, conta):
    conjunto = _conjunto(conta)

    html = admin_logado.get(
        reverse("admin:starchats_conjuntoenvio_change", args=[conjunto.pk])
    ).content.decode()

    assert 'name="limite_diario"' in html
    assert 'name="numeros_permitidos"' in html
    assert 'data-json-widget="tags"' in html
    assert 'name="numero_teste"' in html and 'name="enviar_teste"' in html


def test_salvar_com_envio_de_teste_enfileira_para_o_numero_informado(
    admin_logado, conta, monkeypatch, django_capture_on_commit_callbacks
):
    conjunto = _conjunto(conta)
    chamadas = []
    monkeypatch.setattr(
        "apps.starchats.admin_conjuntos.enfileirar",
        lambda tarefa, *args: chamadas.append((tarefa.name, args)),
    )

    with django_capture_on_commit_callbacks(execute=True):
        resposta = admin_logado.post(
            reverse("admin:starchats_conjuntoenvio_change", args=[conjunto.pk]),
            {
                "nome": conjunto.nome,
                "evento": conjunto.evento,
                "modo": conjunto.modo,
                "modelo": conjunto.modelo_id,
                "limite_diario": "0",
                "numeros_permitidos": "[]",
                "parametros_corpo": (
                    '{"1":"cliente.nome","2":"cliente.email","3":"cliente.email"}'
                ),
                "parametros_cabecalho": "{}",
                "midia_cabecalho_url": "",
                "midia_cabecalho_tipo": "",
                "codigo_botao": "",
                "enviar_uma_vez": "on",
                "active": "on",
                "numero_teste": "(11) 99999-7777",
                "enviar_teste": "on",
                "_save": "Salvar",
            },
        )

    assert resposta.status_code == 302
    assert chamadas == [(
        "apps.starchats.tasks.enviar_teste_starchats",
        (str(conta.pk), conjunto.pk, "(11) 99999-7777"),
    )]
