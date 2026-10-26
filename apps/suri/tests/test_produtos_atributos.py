"""Atributos x dimensions do produto no Suri (HTTP 400 ProductAttributtesAndDimensionsMustMatch).

O SuriFalso (loja_falsa.conferir_produto) recusa como o Suri real: todo envio de produto
dos testes confere a regra.
"""

import pytest

from apps.suri.contexto import usando_configuracao
from apps.suri.importar_catalogo import importar_produto
from apps.suri.tests.loja_falsa import produto
from apps.suri.tests.test_servicos import _config, _enviar, camiseta, montagem  # noqa: F401

pytestmark = pytest.mark.django_db


def test_produto_simples_com_servico_bate_atributos_e_dimensoes(conta, monkeypatch, montagem):  # noqa: F811
    """Falha real ao exportar (COLCHAO HANTARES, APARADOR IBIZA...): "Serviços" ia nos
    atributos e a variacao do proprio produto ia sem ele. Ela vai como "Sem serviço"."""
    from apps.loja.models import Produto

    simples = Produto.objects.get()
    simples.tipo = Produto.Tipo.SIMPLES
    simples.save()
    simples.variantes.exclude(sku="CAM-AZ").delete()
    simples.variantes.get().opcoes.all().delete()

    corpo = _enviar(conta, monkeypatch, simples)

    assert [d["dimensions"] for d in corpo["dimensions"]] == [
        {"Serviços": "Sem serviço"}, {"Serviços": "Montagem"}]


def test_produto_variavel_com_servico_completa_os_outros_atributos(
        conta, monkeypatch, camiseta, montagem):  # noqa: F811
    corpo = _enviar(conta, monkeypatch, camiseta)

    servico = next(d for d in corpo["dimensions"] if d["sku"] == "SERV-MONT")
    assert servico["dimensions"] == {"Cor": "Qualquer", "Serviços": "Montagem"}
    assert next(d for d in corpo["dimensions"] if d["sku"] == "CAM-AZ")["dimensions"] == {
        "Cor": "Azul", "Serviços": "Sem serviço"}


def test_variantes_sem_opcao_e_produto_simples_com_opcao_batem_com_o_suri(
        conta, monkeypatch, camiseta):  # noqa: F811
    """Sem servico tambem falhava: simples com opcao mandava attributes []; variavel sem
    opcoes mandava dimensions {} repetidas."""
    from apps.loja.models import Produto, ValorDaVarianteProduto

    camiseta.tipo = Produto.Tipo.SIMPLES  # mas as variantes tem Cor
    camiseta.save()
    _enviar(conta, monkeypatch, camiseta, enviar=False)
    camiseta.tipo = Produto.Tipo.VARIAVEL
    camiseta.save()
    ValorDaVarianteProduto.objects.all().delete()

    corpo = _enviar(conta, monkeypatch, camiseta, enviar=False)

    titulos = list(camiseta.variantes.order_by("posicao", "id").values_list("titulo", flat=True))
    assert [d["dimensions"] for d in corpo["dimensions"]] == [{"Variação": t} for t in titulos]
    assert corpo["attributes"] == [{"name": "Variação", "options": [{"name": t}
                                                                     for t in titulos]}]


def test_variacao_do_produto_volta_do_suri_sem_virar_opcao_servicos(conta, montagem, camiseta):  # noqa: F811
    """O "Sem serviço" que o envio pos na variacao nao vira opcao da variante no hub."""
    dados = produto()
    dados["attributes"] = [*dados["attributes"], {"name": "Serviços", "options": [
        {"name": "Sem serviço"}, {"name": "Montagem"}]}]
    for dimensao in dados["dimensions"]:
        dimensao["dimensions"] = {**dimensao["dimensions"], "Serviços": "Sem serviço"}

    with usando_configuracao(_config(conta)):
        obj, _ = importar_produto(dados, sobrescrever=True)

    azul = obj.variantes.get(sku="CAM-AZ")
    assert azul.titulo == "Azul"
    assert [o.valor.tipo.nome for o in azul.opcoes.all()] == ["Cor"]
