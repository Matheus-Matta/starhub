"""Telas dos servicos na Shopify: botoes em Loja > Servicos e o Guia dos servicos."""

import pytest
from django.urls import reverse

from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao

pytestmark = pytest.mark.django_db


@pytest.fixture
def cfg(conta):
    return ConfiguracaoIntegracao.objects.create(
        account=conta, plataforma="shopify", dominio_loja="loja.myshopify.com",
        enviar_servicos=True)


def test_botao_exportar_cria_a_tarefa_e_avisa_se_o_envio_esta_desligado(admin_logado, cfg):
    url = reverse("admin:loja_servico_shopify", args=["exportar"])
    assert url in admin_logado.get(reverse("admin:loja_servico_changelist")).content.decode()

    ConfiguracaoIntegracao.objects.filter(pk=cfg.pk).update(enviar_servicos=False)
    admin_logado.post(url)
    assert not ExecucaoIntegracao.objects.exists()

    ConfiguracaoIntegracao.objects.filter(pk=cfg.pk).update(enviar_servicos=True)
    admin_logado.post(url)
    assert ExecucaoIntegracao.objects.get().tipo == ExecucaoIntegracao.Tipo.EXPORTAR_SERVICOS


def test_guia_traz_o_trecho_do_tema_com_o_endereco_desta_loja(admin_logado, cfg):
    html = admin_logado.get(reverse("admin:integracoes_servicos_guia")).content.decode()

    assert f"servicos-publico/{cfg.uuid}/" in html
    assert "{{ product.id }}" in html and "servicos-tema.js" in html
