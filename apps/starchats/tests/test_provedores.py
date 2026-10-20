import pytest

from apps.loja.models import Cliente
from apps.starchats.models import ConjuntoEnvio, ModeloMensagem
from apps.starchats.processamento import processar_evento
from apps.starchats.provedores import ProvedorMensagens, provedores

pytestmark = pytest.mark.django_db


def test_outro_provedor_reutiliza_modelos_regras_e_processamento(conta, monkeypatch):
    """Uma nova API de WhatsApp nao deve precisar copiar o motor de mensagens."""
    modelo = ModeloMensagem.objects.create(
        account=conta,
        plataforma="whatsapp_futuro",
        caixa_entrada_id=77,
        nome="boas_vindas",
        idioma="pt_BR",
        conteudo="Ola {{1}}",
    )
    ConjuntoEnvio.objects.create(
        account=conta,
        nome="Boas-vindas futuras",
        evento="cliente.criado",
        modelo=modelo,
        parametros_corpo={"1": "cliente.nome_completo"},
    )
    cliente = Cliente.objects.create(
        account=conta,
        nome="Lia",
        telefone="81999996666",
    )
    enviados = []
    monkeypatch.setitem(
        provedores,
        "whatsapp_futuro",
        ProvedorMensagens(
            disponivel=lambda _modelo: True,
            enviar=lambda envio, contexto: enviados.append((envio, contexto)) or {"id": 91},
        ),
    )

    resultado = processar_evento(
        str(conta.pk), "cliente", cliente.pk, "cliente.criado", "evento-futuro"
    )

    assert resultado == 1
    assert enviados[0][0].conteudo == "Ola Lia"
