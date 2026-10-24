"""Servicos do hub no Suri: variante do produto na ida, servico do item na volta."""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Categoria, RegraServico, Servico
from apps.loja.services.extras_pedido import extras
from apps.suri import servicos_sinais
from apps.suri.contexto import coletando_avisos, usando_configuracao
from apps.suri.envio.marketplace import SuriMarketplace
from apps.suri.importar_catalogo import importar_produto
from apps.suri.importar_pedidos import importar_pedido
from apps.suri.tests.loja_falsa import SuriFalso, configuracao, pedido, produto

pytestmark = pytest.mark.django_db
ENVIA = tuple((r, o) for r in ("produtos", "categorias") for o in ("create", "update"))
LINHA_SERVICO = {"providerId": "48349", "sku": "SERV-MONT", "name": "Camiseta (Montagem)",
                 "quantity": Decimal("1.0"), "unitPrice": Decimal("30.0"),
                 "totalAmout": Decimal("30.0"), "discountAmout": Decimal("0.0"),
                 "subTotalAmount": Decimal("30.0")}


def _config(conta, enviar=True, receber=True):
    from apps.integracoes.models import ConfiguracaoIntegracao

    cfg = ConfiguracaoIntegracao.objects.filter(plataforma="suri").first() or configuracao(
        conta, enviar=ENVIA)
    cfg.enviar_servicos, cfg.receber_servicos = enviar, receber
    cfg.save()
    return cfg


@pytest.fixture
def camiseta():
    """Produto que ja esta no Suri (vinculo 48349) e numa categoria vinculada."""
    roupas = Categoria.objects.create(nome="Roupas", slug="roupas")
    ExternalReference.objects.create(platform="suri", entity_type="categorias",
                                     external_id="48348", object_id=str(roupas.pk))
    obj, _ = importar_produto(produto())
    obj.categorias.set([roupas])
    return obj


@pytest.fixture
def montagem(camiseta):
    servico = Servico.objects.create(nome="Montagem", sku="SERV-MONT", preco=Decimal("50.00"))
    regra = RegraServico.objects.create(servico=servico, tipo=RegraServico.Tipo.PRODUTO,
                                        preco=Decimal("30.00"))
    regra.produtos.set([camiseta])
    return servico


def _enviar(conta, monkeypatch, obj, **ligado):
    loja = SuriFalso().instalar(monkeypatch)
    SuriMarketplace(_config(conta, **ligado)).enviar("produtos", "update", obj.pk)
    return loja.chamadas[-1][2]


def test_servico_do_produto_vai_como_variante_com_o_sku_e_o_preco_da_regra(
        conta, monkeypatch, camiseta, montagem):
    corpo = _enviar(conta, monkeypatch, camiseta)

    servico = next(d for d in corpo["dimensions"] if d["sku"] == "SERV-MONT")
    assert servico["dimensions"] == {"Servico": "Montagem"}
    assert servico["price"] == Decimal("30.00")
    assert servico["stocks"] == {"48346": {"stock": 5}}, "vende enquanto o produto tiver"
    assert {"name": "Servico", "options": [{"name": "Montagem"}]} in corpo["attributes"]
    assert ExternalReference.objects.get(entity_type="servicos").external_id == (
        "48349:SERV-MONT")


def test_envio_de_servicos_desligado_manda_so_as_variantes_do_produto(
        conta, monkeypatch, camiseta, montagem):
    corpo = _enviar(conta, monkeypatch, camiseta, enviar=False)

    assert [d["sku"] for d in corpo["dimensions"]] == ["CAM-AZ", "CAM-VD"]


def test_tirar_o_produto_da_regra_reenvia_e_a_variante_some(
        conta, monkeypatch, camiseta, montagem, django_capture_on_commit_callbacks):
    """O PUT do Suri troca o produto inteiro: sem reenvio a variante ficava la a venda."""
    _enviar(conta, monkeypatch, camiseta)
    enfileirados = []
    monkeypatch.setattr("apps.integracoes.envio.distribuidor._enfileirar",
                        lambda *args: enfileirados.append(args))

    with django_capture_on_commit_callbacks(execute=True):
        montagem.regras.get().produtos.clear()

    assert [(r, o, pk) for _c, r, o, pk in enfileirados] == [("produtos", "update", camiseta.pk)]
    corpo = _enviar(conta, monkeypatch, camiseta)
    assert "SERV-MONT" not in [d["sku"] for d in corpo["dimensions"]]
    assert not ExternalReference.objects.filter(entity_type="servicos").exists()


def test_regra_nova_por_categoria_reenvia_os_produtos_da_categoria(conta, camiseta):
    _config(conta)
    servico = Servico.objects.create(nome="Garantia", sku="SERV-GAR")
    regra = RegraServico.objects.create(servico=servico)
    regra.categorias.set(camiseta.categorias.all())

    assert servicos_sinais.produtos_afetados(conta.pk, servico.pk) == [camiseta.pk]


def test_item_com_sku_de_servico_vira_servico_do_item_com_o_valor_somado(
        conta, monkeypatch, camiseta, montagem):
    """O total do pedido tem que bater com o do Suri, e o ERP le o servico no item."""
    SuriFalso(produtos=[produto()]).instalar(monkeypatch)
    dados = pedido(items=[*pedido()["items"], LINHA_SERVICO], totalAmount=Decimal("134.8"))

    with usando_configuracao(_config(conta)), coletando_avisos() as avisos:
        obj, _ = importar_pedido(dados)

    item = obj.itens.get()
    assert item.sku == "CAM-AZ" and item.total == Decimal("129.80")
    assert obj.total == Decimal("134.80") and not avisos
    assert extras(obj)["servicos"] == [{
        "item_id": item.pk, "sku": "CAM-AZ", "servico": "Montagem",
        "servico_id": montagem.pk, "opcao": "Sim", "preco": "30.00"}]


def test_receber_servicos_desligado_nao_mexe_nos_servicos_do_pedido(
        conta, monkeypatch, camiseta, montagem):
    """Servico gravado pelo ERP (PUT da API Woo) nao pode sumir no proximo webhook."""
    SuriFalso(produtos=[produto()]).instalar(monkeypatch)
    with usando_configuracao(_config(conta, receber=False)):
        obj, _ = importar_pedido(pedido())
        from apps.loja.services.extras_pedido import mesclar_extras

        mesclar_extras(obj, {"servicos": [{"item_id": 1, "servico": "Montagem"}]})
        obj.save()
        obj, _ = importar_pedido(pedido())

    assert extras(obj)["servicos"] == [{"item_id": 1, "servico": "Montagem"}]


def test_catalogo_do_suri_nao_transforma_o_servico_em_variante(conta, montagem, camiseta):
    dados = produto()
    dados["attributes"] = [*dados["attributes"], {"name": "Servico",
                                                  "options": [{"name": "Montagem"}]}]
    dados["dimensions"] = [*dados["dimensions"], {
        "sku": "SERV-MONT", "dimensions": {"Servico": "Montagem"}, "price": Decimal("30"),
        "stocks": {"48346": {"stock": 5}}}]

    with usando_configuracao(_config(conta)):
        obj, _ = importar_produto(dados, sobrescrever=True)

    assert sorted(obj.variantes.values_list("sku", flat=True)) == ["CAM-AZ", "CAM-VD"]
