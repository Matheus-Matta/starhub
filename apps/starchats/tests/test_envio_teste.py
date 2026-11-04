"""Envio manual de um conjunto para um telefone informado no admin."""

import pytest

from apps.starchats.envio_teste import enviar_teste
from apps.starchats.models import ConjuntoEnvio
from apps.starchats.tests.test_integracao import _configuracao, _modelo

pytestmark = pytest.mark.django_db


def test_envio_teste_usa_numero_informado_e_valores_de_exemplo(conta, monkeypatch):
    configuracao = _configuracao(conta)
    modelo = _modelo(conta, configuracao)
    conjunto = ConjuntoEnvio.objects.create(
        account=conta,
        nome="Teste do pedido",
        evento="pedido.criado",
        modelo=modelo,
        parametros_corpo={
            "1": "cliente.nome_completo",
            "2": "pedido.numero",
            "3": "pedido.total",
        },
    )
    chamadas = []

    class ApiFalsa:
        def __init__(self, _configuracao):
            pass

        def criar_contato(self, dados):
            chamadas.append(("contato", dados))
            return {"contact": {"id": 31}, "contact_inbox": {"source_id": "5511999997777"}}

        def criar_conversa(self, dados):
            chamadas.append(("conversa", dados))
            return {"id": 41}

        def enviar_mensagem(self, conversa_id, dados):
            chamadas.append(("mensagem", conversa_id, dados))
            return {"id": 51}

    monkeypatch.setattr("apps.starchats.envio_teste.ClienteStarChats", ApiFalsa)

    resposta = enviar_teste(conjunto, "(11) 99999-7777")

    assert resposta == {"id": 51}
    assert chamadas[0][1]["phone_number"] == "+5511999997777"
    mensagem = chamadas[-1][2]
    assert mensagem["content"] == "Ola Cliente de teste, o pedido TESTE-001 totaliza R$ 100.00."
    assert mensagem["template_params"]["processed_params"]["body"] == {
        "1": "Cliente de teste",
        "2": "TESTE-001",
        "3": "100.00",
    }
