from decimal import Decimal

import pytest

from apps.loja.models import Cliente, Pedido
from apps.starchats.models import (
    ConfiguracaoStarChats,
    ConjuntoEnvio,
    ModeloMensagem,
    RegraEnvio,
)
from apps.starchats.processamento import processar_evento

pytestmark = pytest.mark.django_db


def _configuracao(conta):
    configuracao = ConfiguracaoStarChats.objects.create(
        account=conta,
        url_base="https://chat.exemplo.com",
        conta_externa_id=12,
        caixa_entrada_id=34,
    )
    configuracao.token_acesso = "token-super-secreto"
    configuracao.save()
    return configuracao


def _modelo(conta, configuracao):
    return ModeloMensagem.objects.create(
        account=conta,
        configuracao=configuracao,
        caixa_entrada_id=34,
        nome="pedido_confirmado",
        idioma="pt_BR",
        categoria="UTILITY",
        conteudo="Ola {{1}}, o pedido {{2}} totaliza R$ {{3}}.",
        componentes=[{"type": "BODY"}],
    )


def test_token_fica_criptografado_no_banco(conta):
    """Uma leitura direta do banco nunca pode revelar o token do StarChats."""
    configuracao = _configuracao(conta)

    configuracao.refresh_from_db()

    assert "token-super-secreto" not in configuracao.token_criptografado
    assert configuracao.token_acesso == "token-super-secreto"


def test_mesma_regra_pode_ser_usada_em_varios_conjuntos(conta):
    """A regra e N:N: uma condicao reutilizavel pode participar de varios fluxos."""
    configuracao = _configuracao(conta)
    modelo = _modelo(conta, configuracao)
    regra = RegraEnvio.objects.create(
        account=conta,
        nome="Aceitou marketing",
        campo="cliente.aceita_marketing",
        operador=RegraEnvio.Operador.IGUAL,
        valor="true",
    )
    primeiro = ConjuntoEnvio.objects.create(
        account=conta, nome="Boas-vindas", evento="cliente.criado", modelo=modelo
    )
    segundo = ConjuntoEnvio.objects.create(
        account=conta, nome="Pos-venda", evento="pedido.criado", modelo=modelo
    )

    primeiro.regras.add(regra)
    segundo.regras.add(regra)

    assert list(regra.conjuntos.order_by("nome").values_list("nome", flat=True)) == [
        "Boas-vindas",
        "Pos-venda",
    ]


def test_evento_renderiza_template_com_dados_do_cliente_e_pedido(
    conta, monkeypatch
):
    """O envio deve usar os campos escolhidos, sem montar texto manual fora do template."""
    configuracao = _configuracao(conta)
    modelo = _modelo(conta, configuracao)
    conjunto = ConjuntoEnvio.objects.create(
        account=conta,
        nome="Confirmacao paga",
        evento="pedido.criado",
        modelo=modelo,
        parametros_corpo={
            "1": "cliente.nome_completo",
            "2": "pedido.numero",
            "3": "pedido.total",
        },
    )
    regra = RegraEnvio.objects.create(
        account=conta,
        nome="Pagamento confirmado",
        campo="pedido.status",
        operador=RegraEnvio.Operador.IGUAL,
        valor="confirmed",
    )
    conjunto.regras.add(regra)
    cliente = Cliente.objects.create(
        account=conta,
        email="ana@example.com",
        nome="Ana",
        sobrenome="Silva",
        telefone="81999998888",
    )
    pedido = Pedido.objects.create(
        account=conta,
        cliente=cliente,
        email=cliente.email,
        telefone=cliente.telefone,
        status=Pedido.Status.CONFIRMADO,
        total=Decimal("129.90"),
    )
    enviados = []
    monkeypatch.setattr(
        "apps.starchats.processamento.enviar_modelo",
        lambda envio, contexto: enviados.append((envio, contexto)) or {"id": 987},
    )

    resultado = processar_evento(
        str(conta.pk), "pedido", pedido.pk, "pedido.criado", "evento-123"
    )

    assert resultado == 1
    assert len(enviados) == 1
    envio = enviados[0][0]
    assert envio.conteudo == f"Ola Ana Silva, o pedido {pedido.number} totaliza R$ 129.90."
    assert envio.parametros == {"1": "Ana Silva", "2": pedido.number, "3": "129.90"}
    assert envio.mensagem_externa_id == "987"


def test_evento_nao_envia_quando_regra_nao_bate(conta, monkeypatch):
    """Um cliente fora das condicoes nao pode receber a mensagem do conjunto."""
    configuracao = _configuracao(conta)
    modelo = _modelo(conta, configuracao)
    conjunto = ConjuntoEnvio.objects.create(
        account=conta,
        nome="Somente marketing",
        evento="cliente.criado",
        modelo=modelo,
        parametros_corpo={"1": "cliente.nome_completo", "2": "cliente.email", "3": "cliente.email"},
    )
    regra = RegraEnvio.objects.create(
        account=conta,
        nome="Aceitou marketing",
        campo="cliente.aceita_marketing",
        operador=RegraEnvio.Operador.IGUAL,
        valor="true",
    )
    conjunto.regras.add(regra)
    cliente = Cliente.objects.create(
        account=conta,
        email="bia@example.com",
        nome="Bia",
        telefone="81999997777",
        aceita_marketing=False,
    )
    enviados = []
    monkeypatch.setattr(
        "apps.starchats.processamento.enviar_modelo",
        lambda *args: enviados.append(args),
    )

    resultado = processar_evento(
        str(conta.pk), "cliente", cliente.pk, "cliente.criado", "evento-456"
    )

    assert resultado == 0
    assert enviados == []
