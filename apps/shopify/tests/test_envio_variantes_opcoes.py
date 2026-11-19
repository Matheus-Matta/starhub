"""Opcoes da variante (Cor, Tamanho) no update para o Shopify.

A opcao vai no lote so se a loja tem aquela opcao; variante nova com opcao que a loja
nao tem fica de fora com aviso, sem derrubar o preco das outras (tarefa #90878,
"Option does not exist").
"""

import pytest

from apps.loja.models import TipoVariante, ValorDaVarianteProduto, ValorVariante
from apps.shopify.tests.test_envio_produtos import PRODUTO_GID, _enviador, _simples
from apps.shopify.tests.test_envio_variantes_vinculo import (
    _chamada,
    _chamou,
    _ids_no_lote,
    _pv,
    _respostas,
    _sofa,
    _vincular,
    _vinculos,
)


@pytest.mark.django_db
def test_opcao_trocada_no_hub_vai_no_update_quando_a_loja_tem_a_opcao(conta):
    """Cor Azul -> Verde no hub: sem optionValues no lote, a loja ficava com Azul."""
    produto, (variante,) = _sofa("SOFA-VD")
    cor = TipoVariante.objects.create(nome="Cor")
    ValorDaVarianteProduto.objects.create(
        variante=variante, valor=ValorVariante.objects.create(tipo=cor, valor="Verde"))
    _vincular(variante, 1)
    enviador = _enviador(conta, _respostas((1, "SOFA-VD"), opcoes=("Cor",)))

    enviador.atualizar(produto, PRODUTO_GID)

    [enviada] = _chamada(enviador, "productVariantsBulkUpdate")["variants"]
    assert enviada["optionValues"] == [{"optionName": "Cor", "name": "Verde"}]


@pytest.mark.django_db
def test_opcao_que_a_loja_nao_tem_nao_vai_no_update(conta):
    """Opcao com outro nome na loja derrubaria o lote inteiro (preco junto)."""
    produto, variante = _simples()
    _vincular(variante, 1)
    enviador = _enviador(conta, _respostas((1, "MESA-1"), opcoes=("Cor",)))

    enviador.atualizar(produto, PRODUTO_GID)

    [enviada] = _chamada(enviador, "productVariantsBulkUpdate")["variants"]
    assert "optionValues" not in enviada


@pytest.mark.django_db
def test_variante_nova_com_opcao_que_a_loja_nao_tem_nao_derruba_o_preco(conta):
    """Tarefa #90878 (COMODA PAOLA): "variants.0.optionValues.0: Option does not exist"
    no create derrubava o envio; o preco da variante vinculada nao chegava."""
    produto, (bege, prata) = _sofa("SOFA-BG", "SOFA-PT")
    _vincular(bege, 1)
    enviador = _enviador(conta, _respostas((1, "SOFA-BG"), opcoes=("Cor",)))

    enviador.atualizar(produto, PRODUTO_GID)

    assert _ids_no_lote(enviador) == [_pv(1)]
    assert not _chamou(enviador, "productVariantsBulkCreate")
    assert _vinculos(prata) == []


@pytest.mark.django_db
def test_lista_cortada_em_250_nao_cria_de_novo_a_variante_ligada(conta, monkeypatch):
    monkeypatch.setattr("apps.shopify.envio.produtos_casar.LIMITE", 1)
    produto, (bege, prata) = _sofa("SOFA-BG", "SOFA-PT")
    _vincular(bege, 1)
    _vincular(prata, 2)
    enviador = _enviador(conta, _respostas((1, "SOFA-BG")))  # a 2 ficou fora da lista

    enviador.atualizar(produto, PRODUTO_GID)

    assert _ids_no_lote(enviador) == [_pv(1), _pv(2)]
    assert not _chamou(enviador, "productVariantsBulkCreate")
