"""Categoria de servico no admin: cadastro proprio e campo na pagina do servico."""

import pytest
from django.urls import reverse

from apps.loja.models import CategoriaServico, Servico

pytestmark = pytest.mark.django_db


def test_categoria_tem_tela_propria_com_os_servicos_dela(admin_logado):
    instalacao = CategoriaServico.objects.create(nome="Instalação", ordem=1)
    Servico.objects.create(nome="Simples", sku="INS1", categoria=instalacao)

    html = admin_logado.get(reverse("admin:loja_categoriaservico_changelist")).content.decode()

    assert "Instalação" in html and "Simples" in html


def test_pagina_do_servico_escolhe_a_categoria(admin_logado):
    instalacao = CategoriaServico.objects.create(nome="Instalação")
    servico = Servico.objects.create(nome="Simples", sku="INS1")

    resposta = admin_logado.post(reverse("admin:loja_servico_change", args=[servico.pk]), {
        "nome": "Simples", "sku": "INS1", "categoria": instalacao.pk, "preco": "20.00",
        "active": "on", "inclusao": "escolha", "_save": "1"})

    assert resposta.status_code == 302, resposta.content.decode()[:2000]
    servico.refresh_from_db()
    assert servico.categoria == instalacao
