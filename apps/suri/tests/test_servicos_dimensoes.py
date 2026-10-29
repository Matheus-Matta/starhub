"""Servico no Suri: Azul (padrao) + Imper vai com o SKU do servico; Verde + Imper, com
"IMP-CAM-VD" (combinacoes em test_servicos_combinacoes.py).

O cliente compra "Imper" e leva a cor escolhida com o servico; o pedido volta ao hub
como o item da cor pelo preco dele e o servico a parte.
"""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Categoria, RegraServico, Servico
from apps.loja.services.extras_pedido import extras
from apps.suri.contexto import usando_configuracao
from apps.suri.envio.marketplace import SuriMarketplace
from apps.suri.importar_catalogo import importar_produto
from apps.suri.importar_pedidos import importar_pedido
from apps.suri.tests.loja_falsa import SuriFalso, configuracao, pedido, produto

pytestmark = pytest.mark.django_db
ENVIA = tuple((r, o) for r in ("produtos", "categorias", "estoque")
              for o in ("create", "update"))


@pytest.fixture
def cfg(conta):
    cfg = configuracao(conta, enviar=ENVIA)
    cfg.enviar_servicos = cfg.receber_servicos = True
    cfg.save()
    return cfg


@pytest.fixture
def camiseta():
    roupas = Categoria.objects.create(nome="Roupas", slug="roupas")
    ExternalReference.objects.create(platform="suri", entity_type="categorias",
                                     external_id="48348", object_id=str(roupas.pk))
    obj, _ = importar_produto(produto())
    obj.categorias.set([roupas])
    return obj


@pytest.fixture
def imper(camiseta):
    servico = Servico.objects.create(nome="Imper", sku="IMP", preco=Decimal("50.00"))
    RegraServico.objects.create(servico=servico, tipo=RegraServico.Tipo.PRODUTO,
                                preco=Decimal("30.00")).produtos.set([camiseta])
    return servico


def _enviar(cfg, monkeypatch, camiseta):
    loja = SuriFalso().instalar(monkeypatch)
    SuriMarketplace(cfg).enviar("produtos", "update", camiseta.pk)
    return loja, loja.chamadas[-1][2]


def test_servico_vai_com_o_sku_dele_e_o_preco_somado_ao_do_produto(
        cfg, monkeypatch, camiseta, imper):
    _, corpo = _enviar(cfg, monkeypatch, camiseta)

    por_sku = {d["sku"]: d for d in corpo["dimensions"]}
    assert list(por_sku) == ["CAM-AZ", "CAM-VD", "IMP", "IMP-CAM-VD"]
    servico, azul = por_sku["IMP"], por_sku["CAM-AZ"]
    assert servico["dimensions"] == {"Cor": "Azul", "Serviço": "Imper (R$ 30,00)"}
    assert azul["dimensions"] == {"Cor": "Azul", "Serviço": "Sem serviço"}
    assert servico["price"] == azul["price"] + Decimal("30.00")
    assert servico["stocks"] == azul["stocks"]
    assert corpo["attributes"] == [
        {"name": "Cor", "options": [{"name": "Azul"}, {"name": "Verde"}]},
        {"name": "Serviço", "options": [{"name": "Sem serviço"},
                                         {"name": "Imper (R$ 30,00)"}]}]
    assert not any("Qualquer" in d["dimensions"].values() for d in corpo["dimensions"])


def test_pedido_do_servico_vira_item_da_variante_padrao_sem_o_valor_do_servico(
        cfg, monkeypatch, camiseta, imper):
    """A linha do Suri cobra produto + servico; no hub o item fica com o preco dele."""
    _enviar(cfg, monkeypatch, camiseta)
    linha = {"providerId": "48349", "sku": "IMP", "name": "Camiseta (Imper)",
             "quantity": Decimal("2"), "unitPrice": Decimal("79.90"),
             "subTotalAmount": Decimal("159.80"), "totalAmout": Decimal("159.80"),
             "discountAmout": Decimal("0")}

    with usando_configuracao(cfg):
        obj, _ = importar_pedido(pedido(items=[linha], totalAmount=Decimal("169.80"),
                                        discountAmount=Decimal("0")))

    item = obj.itens.get()
    assert (item.variante.sku, item.quantidade, item.preco_unitario, item.subtotal,
            item.total) == ("CAM-AZ", 2, Decimal("49.90"), Decimal("99.80"), Decimal("99.80"))
    assert extras(obj)["servicos"] == [{
        "item_id": item.pk, "sku": "CAM-AZ", "servico": "Imper", "servico_id": imper.pk,
        "opcao": "Sim", "preco": "60.00"}]


def test_receber_servicos_desligado_deixa_o_valor_inteiro_no_item(
        cfg, monkeypatch, camiseta, imper):
    _enviar(cfg, monkeypatch, camiseta)
    cfg.receber_servicos = False
    cfg.save()
    linha = {"providerId": "48349", "sku": "IMP", "name": "Camiseta (Imper)",
             "quantity": Decimal("1"), "unitPrice": Decimal("79.90"),
             "subTotalAmount": Decimal("79.90"), "totalAmout": Decimal("79.90")}

    with usando_configuracao(cfg):
        obj, _ = importar_pedido(pedido(items=[linha]))

    item = obj.itens.get()
    assert (item.variante.sku, item.total) == ("CAM-AZ", Decimal("79.90"))


def test_estoque_da_variante_padrao_vai_junto_para_o_servico(
        cfg, monkeypatch, camiseta, imper):
    loja, _ = _enviar(cfg, monkeypatch, camiseta)
    azul = camiseta.variantes.get(sku="CAM-AZ")
    azul.inventory_quantity = 3
    azul.save()

    SuriMarketplace(cfg).enviar("estoque", "update", azul.pk)

    metodo, rota, corpo = loja.chamadas[-1]
    assert (metodo, rota) == ("PUT", "shop/products/48349/stocks")
    assert [s["sku"] for s in corpo["skus"]] == ["CAM-AZ", "IMP"]
    assert {s["stocks"]["48346"]["stock"] for s in corpo["skus"]} == {3}


def test_catalogo_com_servico_sem_vinculo_nao_vira_variante(cfg):
    """Banco novo (sem o vinculo "servicos"): o valor do atributo Serviço ja denuncia."""
    dados = produto()
    dados["attributes"] = [*dados["attributes"], {"name": "Serviço", "options": [
        {"name": "Sem serviço"}, {"name": "Imper (R$ 30,00)"}]}]
    for dimensao in dados["dimensions"]:
        dimensao["dimensions"] = {**dimensao["dimensions"], "Serviço": "Sem serviço"}
    dados["dimensions"].append({"sku": "IMP", "price": Decimal("79.9"),
                                "dimensions": {"Cor": "Azul", "Serviço": "Imper (R$ 30,00)"},
                                "stocks": {"48346": {"stock": 5}}})

    with usando_configuracao(cfg):
        obj, _ = importar_produto(dados)

    assert sorted(obj.variantes.values_list("sku", flat=True)) == ["CAM-AZ", "CAM-VD"]
