"""Limites do conjunto antes de uma mensagem chegar ao provedor."""

import pytest

from apps.loja.models import Cliente
from apps.starchats.models import ConjuntoEnvio
from apps.starchats.processamento import processar_evento
from apps.starchats.tests.test_integracao import _configuracao, _modelo

pytestmark = pytest.mark.django_db


def _cliente(conta, email, telefone):
    return Cliente.objects.create(
        account=conta, email=email, nome="Cliente", telefone=telefone
    )


def _conjunto(conta, **campos):
    configuracao = _configuracao(conta)
    modelo = _modelo(conta, configuracao)
    return ConjuntoEnvio.objects.create(
        account=conta,
        nome="Boas-vindas controladas",
        evento="cliente.criado",
        modelo=modelo,
        parametros_corpo={"1": "cliente.nome", "2": "cliente.email", "3": "cliente.email"},
        **campos,
    )


def test_limite_diario_bloqueia_envios_depois_da_quantidade_configurada(conta, monkeypatch):
    """Eventos diferentes no mesmo dia nao podem ultrapassar o teto do conjunto."""
    _conjunto(conta, limite_diario=1)
    ana = _cliente(conta, "ana@example.com", "81999998888")
    bia = _cliente(conta, "bia@example.com", "81999997777")
    enviados = []
    monkeypatch.setattr(
        "apps.starchats.processamento.enviar_modelo",
        lambda envio, contexto: enviados.append(envio.cliente_id) or {"id": len(enviados)},
    )

    primeiro = processar_evento(
        str(conta.pk), "cliente", ana.pk, "cliente.criado", "evento-ana"
    )
    segundo = processar_evento(
        str(conta.pk), "cliente", bia.pk, "cliente.criado", "evento-bia"
    )

    assert (primeiro, segundo) == (1, 0)
    assert enviados == [ana.pk]


def test_lista_de_numeros_so_envia_para_quem_esta_nela(conta, monkeypatch):
    """A lista aceita formatos com e sem +55, mas bloqueia telefone nao cadastrado."""
    _conjunto(conta, numeros_permitidos=["+55 81 99999-8888", "11999997777"])
    permitido = _cliente(conta, "ana@example.com", "81999998888")
    bloqueado = _cliente(conta, "bia@example.com", "21999996666")
    enviados = []
    monkeypatch.setattr(
        "apps.starchats.processamento.enviar_modelo",
        lambda envio, contexto: enviados.append(envio.cliente_id) or {"id": 1},
    )

    aceito = processar_evento(
        str(conta.pk), "cliente", permitido.pk, "cliente.criado", "permitido"
    )
    recusado = processar_evento(
        str(conta.pk), "cliente", bloqueado.pk, "cliente.criado", "bloqueado"
    )

    assert (aceito, recusado) == (1, 0)
    assert enviados == [permitido.pk]
