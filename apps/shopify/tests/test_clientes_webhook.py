"""Webhook REST customers/create|update e busca GraphQL chegam ao mesmo cadastro."""

import pytest

from apps.core.models import ExternalReference
from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao, ExecucaoIntegracao
from apps.loja.models import Cliente
from apps.shopify import recursos
from apps.shopify.tasks import processar_webhook_shopify
from apps.shopify.tests import cliente_exemplo
from apps.shopify.webhooks import processar_webhook

pytestmark = pytest.mark.django_db

CAMPOS = ("email", "nome", "sobrenome", "telefone", "notas", "aceita_marketing", "locale",
          "empresa", "isento_imposto", "cliente_pagante", "created_at")
ENDERECO = ("address_line_1", "address_line_2", "number", "neighborhood", "city", "state_code",
            "postal_code", "country_code", "phone", "company", "recipient_name")


def _retrato():
    cliente = Cliente.objects.get()
    vinculos = sorted(
        (v.tipo, v.padrao, tuple(getattr(v.endereco, campo) for campo in ENDERECO))
        for v in cliente.vinculos_endereco.select_related("endereco")
    )
    metadata = ExternalReference.objects.get(entity_type="clientes").metadata
    return {campo: getattr(cliente, campo) for campo in CAMPOS}, vinculos, metadata


def test_webhook_rest_e_graphql_dao_o_mesmo_cliente():
    """Antes o webhook so trocava first/last_name: endereco e marketing se perdiam."""
    recursos.cliente(cliente_exemplo.graphql())
    pelo_graphql = _retrato()
    Cliente.objects.all().delete()
    ExternalReference.objects.all().delete()

    processar_webhook(None, "clientes", "create", cliente_exemplo.rest(), lambda *_: None)

    assert _retrato() == pelo_graphql


def test_webhook_update_aplica_endereco_e_consentimento():
    recursos.cliente(cliente_exemplo.graphql())
    dados = cliente_exemplo.rest(email_marketing_consent={"state": "unsubscribed"})
    dados["addresses"][0]["zip"] = "50000-000"

    mensagem = processar_webhook(None, "clientes", "update", dados, lambda *_: None)

    cliente = Cliente.objects.get()
    assert mensagem == "Registro atualizado."
    assert cliente.aceita_marketing is False
    ceps = set(cliente.enderecos.values_list("postal_code", flat=True))
    assert "50000000" in ceps


def _configuracao_que_envia_clientes(conta):
    matriz = permissoes.matriz_vazia()
    matriz["receber"]["clientes"]["create"] = True
    matriz["enviar"]["clientes"]["create"] = matriz["enviar"]["clientes"]["update"] = True
    return ConfiguracaoIntegracao.objects.create(
        account=conta, nome="Loja", plataforma="shopify", permissoes=matriz)


def test_importacao_pela_tarefa_nao_ecoa_para_o_shopify(
    conta, monkeypatch, django_capture_on_commit_callbacks
):
    """Gravado como origem shopify: se agendasse envio, o cliente voltaria ao Shopify
    e o customers/update dele dispararia outra importacao, sem fim."""
    agendados = []
    monkeypatch.setattr("apps.integracoes.envio.distribuidor._enfileirar",
                        lambda *args: agendados.append(args))
    configuracao = _configuracao_que_envia_clientes(conta)
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=configuracao, tipo=ExecucaoIntegracao.Tipo.RECEBER)

    with django_capture_on_commit_callbacks(execute=True):
        resultado = processar_webhook_shopify.run(
            str(execucao.pk), "clientes", "create", cliente_exemplo.rest())

    assert resultado["status"] == "completed"
    assert Cliente.objects.get().cliente_pagante is True
    assert agendados == []


def test_mesma_importacao_fora_da_tarefa_agendaria_envio(
    conta, monkeypatch, django_capture_on_commit_callbacks
):
    """Controle do teste acima: prova que a configuracao dele de fato enviaria."""
    agendados = []
    monkeypatch.setattr("apps.integracoes.envio.distribuidor._enfileirar",
                        lambda *args: agendados.append(args))
    _configuracao_que_envia_clientes(conta)

    with django_capture_on_commit_callbacks(execute=True):
        processar_webhook(None, "clientes", "create", cliente_exemplo.rest(), lambda *_: None)

    assert agendados
