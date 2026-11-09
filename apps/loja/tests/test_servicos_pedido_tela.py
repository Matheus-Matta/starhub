"""Servicos do pedido editados na tela do pedido (card "Servicos do pedido").

Antes os servicos so apareciam no JSON cru de metadados (Avancado): nao dava para
adicionar, trocar nem remover. Servico mexido na tela soma no item, como o que vem da
loja ("somado"): Sofa 1500 + Montagem 80 adicionada = item 1580 e pedido + 80.
"""

from decimal import Decimal

import pytest

from apps.loja.models import ItemPedido, Pedido, Servico
from apps.loja.services import servicos_pedido as tela
from apps.loja.services.extras_pedido import extras, mesclar_extras
from apps.loja.services.variantes import criar_produto
from apps.loja.totais import recalcular_totais

pytestmark = pytest.mark.django_db


@pytest.fixture
def pedido(conta):
    return criar_pedido_com_servicos()


def criar_pedido_com_servicos():
    """Sofa 1580 (Montagem 80 somada) e Mesa 300 (Garantia 50 so informada)."""
    sofa = criar_produto("Sofa", sku="SOF-1", price=Decimal("1500.00"))
    mesa = criar_produto("Mesa", sku="MES-1", price=Decimal("300.00"))
    montagem = Servico.objects.create(nome="Montagem", sku="SERV-MONT", preco=Decimal("80"))
    garantia = Servico.objects.create(nome="Garantia", sku="SERV-GAR", preco=Decimal("50"))
    pedido = Pedido.objects.create(status="processing")
    item_sofa = ItemPedido.objects.create(
        pedido=pedido, produto=sofa, nome="Sofa", sku="SOF-1", quantidade=1,
        subtotal=Decimal("1580.00"), total=Decimal("1580.00"))
    item_mesa = ItemPedido.objects.create(
        pedido=pedido, produto=mesa, nome="Mesa", sku="MES-1", quantidade=1,
        subtotal=Decimal("300.00"), total=Decimal("300.00"))
    mesclar_extras(pedido, {"servicos": [
        {"item_id": item_sofa.pk, "sku": "SOF-1", "servico": "Montagem",
         "servico_id": montagem.pk, "opcao": "Sim", "preco": "80.00", "somado": True},
        {"item_id": item_mesa.pk, "sku": "MES-1", "servico": "Garantia",
         "servico_id": garantia.pk, "opcao": "Sim", "preco": "50.00"},
    ]})
    pedido.save()
    recalcular_totais(pedido)
    return pedido, item_sofa, item_mesa, montagem, garantia


def _servicos(pedido):
    return extras(Pedido.objects.get(pk=pedido.pk))["servicos"]


def _linhas(pedido):
    return tela.linhas_da_tela(Pedido.objects.get(pk=pedido.pk))


def _aplicar(pedido, linhas):
    atual = Pedido.objects.get(pk=pedido.pk)
    tela.aplicar(pedido.pk, linhas, tela.versao(atual))


def _totais(*itens):
    for item in itens:
        item.refresh_from_db()
    return [item.total for item in itens]


def test_adicionar_servico_soma_no_item_e_no_pedido(pedido):
    obj, sofa, mesa, montagem, _ = pedido
    linhas = _linhas(obj) + [{"item_id": str(mesa.pk), "servico_id": str(montagem.pk),
                              "opcao": "", "preco": "80.00"}]

    _aplicar(obj, linhas)

    assert _totais(mesa) == [Decimal("380.00")]
    assert Pedido.objects.get(pk=obj.pk).total == Decimal("1960.00")
    novo = _servicos(obj)[-1]
    assert novo == {"item_id": mesa.pk, "sku": "MES-1", "servico": "Montagem",
                    "servico_id": montagem.pk, "opcao": "Sim", "preco": "80.00",
                    "somado": True}


def test_remover_servico_somado_tira_o_valor_do_item(pedido):
    obj, sofa, *_ = pedido

    _aplicar(obj, _linhas(obj)[1:])

    assert _totais(sofa) == [Decimal("1500.00")]
    assert [s["servico"] for s in _servicos(obj)] == ["Garantia"]


def test_mudar_preco_e_item_do_servico_somado_move_a_diferenca(pedido):
    obj, sofa, mesa, *_ = pedido
    linhas = _linhas(obj)
    linhas[0].update(item_id=str(mesa.pk), preco="100.00")

    _aplicar(obj, linhas)

    assert _totais(sofa, mesa) == [Decimal("1500.00"), Decimal("400.00")]
    assert _servicos(obj)[0]["sku"] == "MES-1"


def test_servico_so_informado_editado_nao_mexe_no_total(pedido):
    """Garantia veio da loja sem somar: o cliente nao pagou a mais por ela no item."""
    obj, _, mesa, *_ = pedido
    linhas = _linhas(obj)
    linhas[1]["preco"] = "70.00"

    _aplicar(obj, linhas)

    assert _totais(mesa) == [Decimal("300.00")]
    assert _servicos(obj)[1]["preco"] == "70.00" and "somado" not in _servicos(obj)[1]


def test_salvar_sem_mexer_mantem_os_servicos_como_estavam(pedido):
    obj, *_ = pedido
    antes = _servicos(obj)

    _aplicar(obj, _linhas(obj))

    assert _servicos(obj) == antes


def test_servicos_mudados_por_webhook_nao_sao_sobrescritos(pedido):
    """A tela aberta antes do webhook gravaria por cima do servico que acabou de chegar."""
    obj, *_ = pedido
    versao_da_tela = tela.versao(Pedido.objects.get(pk=obj.pk))
    atual = Pedido.objects.get(pk=obj.pk)
    mesclar_extras(atual, {"servicos": _servicos(obj)[:1]})
    atual.save()

    with pytest.raises(tela.ServicosMudaram):
        tela.aplicar(obj.pk, [], versao_da_tela)

    assert len(_servicos(obj)) == 1


def test_servico_sem_cadastro_novo_e_recusado(pedido):
    obj, sofa, *_ = pedido
    linhas = _linhas(obj) + [{"item_id": str(sofa.pk), "servico_id": "", "preco": "10"}]

    with pytest.raises(tela.ServicoInvalido, match="Escolha o servico"):
        _aplicar(obj, linhas)


def _orfao(obj):
    """Servico cujo item saiu do pedido (ex.: o ERP trocou o item)."""
    atual = Pedido.objects.get(pk=obj.pk)
    servicos = _servicos(obj)
    servicos[1]["item_id"] = 999999
    mesclar_extras(atual, {"servicos": servicos})
    atual.save()


def test_servico_sem_item_aparece_vazio_para_escolher(pedido):
    """Mostrar o id velho como "Item removido" deixava o servico sem vinculo para sempre."""
    obj, *_ = pedido
    _orfao(obj)

    assert [linha["item_id"] for linha in _linhas(obj)][1] == ""


def test_linha_sem_item_e_recusada_mesmo_sem_mexer(pedido):
    obj, *_ = pedido
    _orfao(obj)

    with pytest.raises(tela.ServicoInvalido, match="Escolha o item"):
        _aplicar(obj, _linhas(obj))
