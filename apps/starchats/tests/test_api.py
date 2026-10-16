import pytest

from apps.loja.models import Cliente
from apps.starchats.envio import enviar_modelo
from apps.starchats.models import (
    ConfiguracaoStarChats,
    ConjuntoEnvio,
    EnvioStarChats,
    ModeloMensagem,
)
from apps.starchats.renderizacao import mapear
from apps.starchats.sincronizacao import sincronizar

pytestmark = pytest.mark.django_db


def test_cabecalho_nomeado_pode_usar_dado_do_cliente():
    """Templates com variavel nomeada no cabecalho recebem o cadastro do cliente."""
    contexto = {"cliente": {"nome_completo": "Ana Silva"}}

    resultado = mapear({"cliente_nome": "cliente.nome_completo"}, contexto)

    assert resultado == {"cliente_nome": "Ana Silva"}


def _configuracao(conta):
    configuracao = ConfiguracaoStarChats.objects.create(
        account=conta,
        url_base="https://chat.exemplo.com",
        conta_externa_id=12,
    )
    configuracao.token_acesso = "segredo"
    configuracao.save()
    return configuracao


def test_sincronizacao_traz_somente_caixa_whatsapp_e_seus_modelos(conta, monkeypatch):
    """Caixas de site ou e-mail nao podem aparecer na selecao do StarChats."""
    configuracao = _configuracao(conta)

    class ApiFalsa:
        def __init__(self, _configuracao):
            pass

        def caixas(self):
            return {"payload": [
                {"id": 10, "name": "Site", "channel_type": "Channel::WebWidget"},
                {"id": 20, "name": "WhatsApp Vendas", "channel_type": "Channel::Whatsapp"},
            ]}

        def modelos(self, caixa_id):
            assert caixa_id == 20
            return {"payload": [{
                "id": "tpl-1",
                "name": "boas_vindas",
                "language": "pt_BR",
                "category": "UTILITY",
                "status": "APPROVED",
                "components": [{"type": "BODY", "text": "Ola {{1}}"}],
            }]}

    monkeypatch.setattr("apps.starchats.sincronizacao.ClienteStarChats", ApiFalsa)

    total = sincronizar(configuracao)

    configuracao.refresh_from_db()
    assert total == 1
    assert configuracao.caixa_entrada_id == 20
    assert configuracao.caixas_disponiveis == [{"id": 20, "nome": "WhatsApp Vendas"}]
    modelo = ModeloMensagem.objects.get()
    assert (modelo.nome, modelo.conteudo, modelo.situacao) == (
        "boas_vindas",
        "Ola {{1}}",
        "APPROVED",
    )


def test_envio_usa_template_oficial_com_corpo_cabecalho_e_botao(conta, monkeypatch):
    """O payload deve preservar a estrutura oficial exigida pelo canal WhatsApp."""
    configuracao = _configuracao(conta)
    configuracao.caixa_entrada_id = 20
    configuracao.save()
    modelo = ModeloMensagem.objects.create(
        account=conta,
        configuracao=configuracao,
        caixa_entrada_id=20,
        nome="cupom_cliente",
        idioma="pt_BR",
        categoria="MARKETING",
        conteudo="Ola {{1}}, use seu cupom.",
    )
    conjunto = ConjuntoEnvio.objects.create(
        account=conta,
        nome="Cupom",
        evento="cliente.criado",
        modelo=modelo,
        parametros_corpo={"1": "cliente.nome_completo"},
        midia_cabecalho_url="https://cdn.example.com/cupom.png",
        midia_cabecalho_tipo="image",
        codigo_botao="BEMVINDO20",
    )
    cliente = Cliente.objects.create(
        account=conta,
        nome="Ana",
        sobrenome="Silva",
        email="ana@example.com",
        telefone="81999998888",
    )
    envio = EnvioStarChats.objects.create(
        account=conta,
        conjunto=conjunto,
        cliente=cliente,
        tipo_objeto="cliente",
        objeto_id=str(cliente.pk),
        evento="cliente.criado",
        chave_deduplicacao="teste-payload",
        conteudo="Ola Ana Silva, use seu cupom.",
        parametros={"1": "Ana Silva"},
    )
    chamadas = []

    class ApiFalsa:
        def __init__(self, _configuracao):
            pass

        def criar_contato(self, dados):
            chamadas.append(("contato", dados))
            return {"payload": {"contact": {"id": 31},
                                "contact_inbox": {"source_id": "5581999998888"}}}

        def criar_conversa(self, dados):
            chamadas.append(("conversa", dados))
            return {"id": 41}

        def enviar_mensagem(self, conversa_id, dados):
            chamadas.append(("mensagem", conversa_id, dados))
            return {"id": 51}

    monkeypatch.setattr("apps.starchats.envio.ClienteStarChats", ApiFalsa)

    resposta = enviar_modelo(envio, {"cliente": {"nome_completo": "Ana Silva"}})

    assert resposta == {"id": 51}
    assert chamadas[0][1]["phone_number"] == "+5581999998888"
    payload = chamadas[-1][2]
    assert payload["template_params"] == {
        "name": "cupom_cliente",
        "category": "MARKETING",
        "language": "pt_BR",
        "processed_params": {
            "body": {"1": "Ana Silva"},
            "header": {
                "media_url": "https://cdn.example.com/cupom.png",
                "media_type": "image",
            },
            "buttons": [{"type": "copy_code", "parameter": "BEMVINDO20"}],
        },
    }
