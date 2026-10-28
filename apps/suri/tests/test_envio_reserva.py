"""Produto incompleto no hub ainda vai ao Suri: categoria, foto e servico de reserva."""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import Categoria, MidiaProduto, RegraServico, Servico
from apps.suri.envio.marketplace import SuriMarketplace
from apps.suri.importar_catalogo import importar_produto
from apps.suri.tests.loja_falsa import SuriFalso, configuracao, produto

pytestmark = pytest.mark.django_db
ENVIA = tuple((r, o) for r in ("produtos", "categorias") for o in ("create", "update"))
FOTO_PADRAO = "https://hub.test/static/starhub/img/logo-600.png"


def _enviar(conta, monkeypatch, obj, servicos=False):
    from apps.integracoes.models import ConfiguracaoIntegracao

    cfg = ConfiguracaoIntegracao.objects.filter(plataforma="suri").first() or configuracao(
        conta, enviar=ENVIA)
    cfg.enviar_servicos = servicos
    cfg.save()
    loja = SuriFalso().instalar(monkeypatch)
    SuriMarketplace(cfg).enviar("produtos", "create", obj.pk)
    return loja


def _produto_sem_categoria():
    obj, _ = importar_produto(produto())
    ExternalReference.objects.filter(platform="suri").delete()
    obj.categorias.clear()
    return obj


def test_produto_sem_categoria_vai_na_categoria_default_com_descricao(conta, monkeypatch):
    """O Suri recusa categoria nula ou vazia; sem categoria o produto nem subia."""
    obj = _produto_sem_categoria()

    loja = _enviar(conta, monkeypatch, obj)
    _enviar(conta, monkeypatch, _produto_sem_categoria())

    padrao = Categoria.objects.get(slug="default")
    assert padrao.nome == "default"
    assert Categoria.objects.filter(slug="default").count() == 1
    categoria = next(c for m, r, c in loja.chamadas if r == "shop/categories")
    assert categoria["name"] == "default" and categoria["description"]
    assert loja.chamadas[-1][2]["categoryId"] == f"sh-{padrao.pk}"


def test_categoria_sem_descricao_vai_com_o_nome_no_lugar(conta, monkeypatch):
    obj = _produto_sem_categoria()
    obj.categorias.set([Categoria.objects.create(nome="Moveis", slug="moveis")])

    loja = _enviar(conta, monkeypatch, obj)

    categoria = next(c for m, r, c in loja.chamadas if r == "shop/categories")
    assert categoria["description"] == "Moveis"


def test_produto_sem_foto_vai_com_a_foto_padrao_em_toda_dimension(conta, monkeypatch):
    """Lista de imagens vazia ou url vazia faziam o Suri falhar com (Parameter 'source')."""
    loja = _enviar(conta, monkeypatch, _produto_sem_categoria())

    corpo = loja.chamadas[-1][2]
    assert [i["url"] for i in corpo["images"]] == [FOTO_PADRAO]
    assert {d["image"]["url"] for d in corpo["dimensions"]} == {FOTO_PADRAO}


def test_variante_e_servico_sem_foto_usam_a_primeira_foto_do_produto(conta, monkeypatch):
    obj = _produto_sem_categoria()
    MidiaProduto.objects.create(produto=obj, tipo=MidiaProduto.Tipo.IMAGEM,
                                url="/media/produtos/sofa.png", posicao=0)
    servico = Servico.objects.create(nome="Montagem", sku="8875", preco=Decimal("49.99"))
    RegraServico.objects.create(servico=servico, tipo=RegraServico.Tipo.PRODUTO).produtos.set(
        [obj])

    corpo = _enviar(conta, monkeypatch, obj, servicos=True).chamadas[-1][2]

    foto = "https://hub.test/media/produtos/sofa.png"
    assert [i["url"] for i in corpo["images"]] == [foto]
    assert {d["sku"]: d["image"]["url"] for d in corpo["dimensions"]} == {
        "CAM-AZ": foto, "CAM-VD": foto, "8875": foto}


def test_servico_ignorado_no_suri_nao_vira_variante(conta, monkeypatch):
    """Montagem gratis que entra sozinha no pedido nao precisa ser escolhida na loja."""
    obj = _produto_sem_categoria()
    servico = Servico.objects.create(nome="Montagem", sku="8875", preco=Decimal("0.00"),
                                     fora_das_integracoes=["suri"])
    RegraServico.objects.create(servico=servico, tipo=RegraServico.Tipo.PRODUTO).produtos.set(
        [obj])

    corpo = _enviar(conta, monkeypatch, obj, servicos=True).chamadas[-1][2]

    assert [d["sku"] for d in corpo["dimensions"]] == ["CAM-AZ", "CAM-VD"]


def test_regra_inativa_nao_manda_o_servico_como_variante(conta, monkeypatch):
    """A regra 10 do espelho estava com Ativo desligado: o servico nao vai, por desenho."""
    obj = _produto_sem_categoria()
    servico = Servico.objects.create(nome="Espelho", sku="8875", preco=Decimal("49.99"))
    RegraServico.objects.create(servico=servico, tipo=RegraServico.Tipo.PRODUTO,
                                active=False).produtos.set([obj])

    corpo = _enviar(conta, monkeypatch, obj, servicos=True).chamadas[-1][2]

    assert [d["sku"] for d in corpo["dimensions"]] == ["CAM-AZ", "CAM-VD"]


def test_servico_ignorado_so_na_shopify_continua_indo_ao_suri(conta, monkeypatch):
    obj = _produto_sem_categoria()
    servico = Servico.objects.create(nome="Montagem", sku="8875", preco=Decimal("0.00"),
                                     fora_das_integracoes=["shopify"])
    RegraServico.objects.create(servico=servico, tipo=RegraServico.Tipo.PRODUTO).produtos.set(
        [obj])

    corpo = _enviar(conta, monkeypatch, obj, servicos=True).chamadas[-1][2]

    assert "8875" in [d["sku"] for d in corpo["dimensions"]]
