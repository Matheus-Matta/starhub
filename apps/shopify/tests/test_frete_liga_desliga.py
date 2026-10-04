"""Liga/desliga do frete do hub no checkout: vale na hora no hub e depois na Shopify."""

from unittest.mock import Mock

import pytest

from apps.core.models import ExternalReference
from apps.integracoes import admin as admin_integracoes
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.shopify.tests.test_frete_cadastro import (
    GID,
    LojaFalsa,
    _cadastrar,
    configuracao,  # noqa: F401 (fixture)
)
from apps.shopify.tests.test_frete_checkout import CHECKOUT, _faixa, _post

pytestmark = pytest.mark.django_db
PAGINA = "/admin/integracoes/configuracaointegracao/shopify/"


def test_desligado_a_rota_responde_sem_opcoes_na_hora(client, configuracao):  # noqa: F811
    """A Shopify ainda pode chamar ate a tarefa atualizar la: o hub ja nao oferece nada."""
    _faixa()
    assert _post(client, configuracao, CHECKOUT).json()["rates"]
    ConfiguracaoIntegracao.objects.filter(pk=configuracao.pk).update(frete_ativo=False)
    configuracao.refresh_from_db()
    assert _post(client, configuracao, CHECKOUT).json() == {"rates": []}


def test_cadastro_manda_active_conforme_o_liga_desliga(configuracao):  # noqa: F811
    configuracao.frete_ativo = False
    loja = LojaFalsa()
    _cadastrar(configuracao, loja)
    assert loja.chamadas[-1][1]["input"]["active"] is False


def _botao(admin_logado, configuracao, acao, monkeypatch):  # noqa: F811
    tarefa = Mock()
    tarefa.delay.return_value = Mock(id="c1")
    monkeypatch.setitem(admin_integracoes.ACOES, "frete",
                        (ExecucaoIntegracao.Tipo.FRETE_CHECKOUT, tarefa))
    admin_logado.post(PAGINA, {"acao": acao, "dominio_loja": "loja.myshopify.com",
                               "url_webhook": configuracao.url_webhook, "active": "on"})
    return tarefa


def test_desligar_cadastrado_atualiza_a_shopify_numa_tarefa(admin_logado, configuracao,  # noqa: F811
                                                            monkeypatch):
    ExternalReference.objects.create(platform="shopify", entity_type="carrier_service",
                                     object_id=str(configuracao.pk), external_id=GID)
    tarefa = _botao(admin_logado, configuracao, "frete_desativar", monkeypatch)
    assert ConfiguracaoIntegracao.objects.get(pk=configuracao.pk).frete_ativo is False
    assert tarefa.delay.called  # a Shopify para de chamar o hub


def test_desligar_sem_cadastro_nao_chama_a_shopify_e_ligar_cadastra(
        admin_logado, configuracao, monkeypatch):  # noqa: F811
    tarefa = _botao(admin_logado, configuracao, "frete_desativar", monkeypatch)
    assert not tarefa.delay.called
    tarefa = _botao(admin_logado, configuracao, "frete_ativar", monkeypatch)
    assert ConfiguracaoIntegracao.objects.get(pk=configuracao.pk).frete_ativo is True
    assert tarefa.delay.called


def test_card_mostra_o_estado_e_o_botao_certo(admin_logado, configuracao):  # noqa: F811
    html = admin_logado.get(PAGINA).content.decode()
    assert 'value="frete_desativar"' in html and "Frete ligado" in html
    ConfiguracaoIntegracao.objects.filter(pk=configuracao.pk).update(frete_ativo=False)
    html = admin_logado.get(PAGINA).content.decode()
    assert 'value="frete_ativar"' in html and "Frete desligado" in html


def test_checklist_mostra_desligado_como_aviso_e_nao_como_erro(configuracao):  # noqa: F811
    from apps.shopify.frete_checklist import checklist

    configuracao.frete_ativo = False
    item = {i["titulo"]: i for i in checklist(configuracao)["itens"]}[
        "Frete do StarHub cadastrado na loja"]
    assert item["estado"] == "aviso" and "Desligado no hub" in item["detalhe"]
