"""Atributos x dimensions do produto no Suri (HTTP 400 ProductAttributtesAndDimensionsMustMatch).

O SuriFalso (loja_falsa.conferir_produto) recusa como o Suri real: todo envio de produto
dos testes confere a regra.
"""

import pytest

from apps.integracoes import exportar as exportador
from apps.loja.models import RegraServico, Servico
from apps.suri.contexto import usando_configuracao
from apps.suri.importar_catalogo import importar_produto
from apps.suri.tests.loja_falsa import SuriFalso, produto
from apps.suri.tests.test_servicos import _config, _enviar, camiseta, montagem  # noqa: F401

pytestmark = pytest.mark.django_db


def test_exportar_produtos_cria_a_variacao_servico(
        conta, monkeypatch, camiseta, montagem):  # noqa: F811
    loja = SuriFalso().instalar(monkeypatch)
    resumo = exportador.exportar_dados(_config(conta), ["produtos"], lambda *_: None)

    corpo = next(c for metodo, rota, c in loja.chamadas
                 if metodo == "PUT" and rota == "shop/products")
    assert resumo.enviados == 1
    por_sku = {d["sku"]: d for d in corpo["dimensions"]}
    servico, azul = por_sku["SERV-MONT"], por_sku["CAM-AZ"]
    assert servico["dimensions"] == {"Cor": "Azul", "Serviço": "Montagem (R$ 30,00)"}
    assert servico["image"] == {"providerId": None, "description": "Camiseta",
                                "url": "https://hub.test/static/starhub/img/logo-600.png"}
    assert servico["measurements"] == azul["measurements"]
    assert servico["priceTables"] == {}
    assert servico["stocks"] == azul["stocks"]


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
        {"Serviço": "Sem serviço"}, {"Serviço": "Montagem (R$ 30,00)"}]


def test_produto_variavel_com_servico_leva_a_cor_da_variante_padrao_no_servico(
        conta, monkeypatch, camiseta, montagem):  # noqa: F811
    """O Suri exige valor em todo atributo; "Cor: Qualquer" era uma opcao falsa a venda."""
    corpo = _enviar(conta, monkeypatch, camiseta)

    servico = next(d for d in corpo["dimensions"] if d["sku"] == "SERV-MONT")
    assert servico["dimensions"] == {"Cor": "Azul", "Serviço": "Montagem (R$ 30,00)"}
    assert not any("Qualquer" in d["dimensions"].values() for d in corpo["dimensions"])
    assert next(d for d in corpo["dimensions"] if d["sku"] == "CAM-AZ")["dimensions"] == {
        "Cor": "Azul", "Serviço": "Sem serviço"}


def test_tipo_servico_recebe_cada_titulo_como_opcao_e_variante(
        conta, monkeypatch, camiseta, montagem):  # noqa: F811
    garantia = Servico.objects.create(nome="Garantia", sku="GAR", preco="20.00")
    regra = RegraServico.objects.create(servico=garantia, tipo=RegraServico.Tipo.PRODUTO)
    regra.produtos.set([camiseta])

    corpo = _enviar(conta, monkeypatch, camiseta)

    atributo = next(a for a in corpo["attributes"] if a["name"] == "Serviço")
    assert atributo["options"] == [
        {"name": "Sem serviço"}, {"name": "Garantia (R$ 20,00)"},
        {"name": "Montagem (R$ 30,00)"}]
    servicos = [d for d in corpo["dimensions"] if d["dimensions"]["Serviço"] != "Sem serviço"]
    assert [(d["sku"], d["dimensions"]["Serviço"], d["stocks"]["48346"]["stock"])
            for d in servicos] == [
                ("GAR", "Garantia (R$ 20,00)", 5), ("SERV-MONT", "Montagem (R$ 30,00)", 5)]


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
        dimensao["dimensions"] = {**dimensao["dimensions"], "Serviço": "Sem serviço"}

    with usando_configuracao(_config(conta)):
        obj, _ = importar_produto(dados, sobrescrever=True)

    azul = obj.variantes.get(sku="CAM-AZ")
    assert azul.titulo == "Azul"
    assert [o.valor.tipo.nome for o in azul.opcoes.all()] == ["Cor"]


def test_variante_sem_a_opcao_das_outras_vai_pelo_titulo_e_nunca_como_qualquer(
        conta, monkeypatch, camiseta):  # noqa: F811
    """"Cor: Qualquer" aparecia como opcao a venda na pagina do produto no Suri."""
    camiseta.variantes.get(sku="CAM-VD").opcoes.all().delete()

    corpo = _enviar(conta, monkeypatch, camiseta, enviar=False)

    titulos = list(camiseta.variantes.order_by("posicao", "id").values_list("titulo", flat=True))
    assert [d["dimensions"] for d in corpo["dimensions"]] == [{"Variação": t} for t in titulos]
