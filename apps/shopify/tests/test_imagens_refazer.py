"""Sincronizar > Importar e > Exportar: as fotos do destino saem e entram as da origem."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.core.models import ExternalReference
from apps.loja.models import VarianteProduto
from apps.shopify.cliente import ShopifyErro
from apps.shopify.envio import produtos_midias_refazer as exportar
from apps.shopify.imagens_baixar import ImagemShopifyErro
from apps.shopify.imagens_refazer import refazer as importar
from apps.shopify.tests.test_envio_midias import _respostas_update, _vincular_variante
from apps.shopify.tests.test_envio_produtos import PRODUTO_GID, _enviador
from apps.shopify.tests.test_imagens_dois_sentidos import (
    PRODUTO,
    Loja,
    cdn,
    da_loja,
    foto,
    gid,
    mesa_na_loja,  # noqa: F401 - fixture "mesa"
    urls,
)

pytestmark = pytest.mark.django_db


def puxar(produto, *fotos, das_variantes=None, falha=False, status="READY"):
    nos = [{"id": v, "media": {"nodes": [{"id": gid(f)}]}}
           for v, f in (das_variantes or {}).items()]
    loja = SimpleNamespace(graphql=lambda *_: {"product": {"variants": {"nodes": nos}}})

    def baixar(url, **_):
        if falha and url == cdn(fotos[-1]):
            raise ImagemShopifyErro("nao baixou.")
        nome = url.rsplit("/", 1)[1]
        return default_storage.url(default_storage.save(
            f"produtos/{nome}", ContentFile(nome.encode())))

    dados = {"id": PRODUTO, "media": {"nodes": [
        {"id": gid(n), "alt": "", "status": status, "image": {"url": cdn(n)}} for n in fotos]}}
    with patch("apps.shopify.imagens_refazer._baixar", side_effect=baixar), \
            patch("apps.shopify.midias.cliente_da_loja", return_value=loja):
        importar(produto, dados)


def test_importar_apaga_as_do_hub_e_traz_as_da_loja(mesa):
    foto(mesa.variante, 8), da_loja(mesa.variante, 1)
    puxar(mesa.produto, 1, 2)
    assert urls(mesa.produto) == ["/media/produtos/1.png", "/media/produtos/2.png"]
    ligadas = ExternalReference.objects.filter(entity_type="midias")
    assert {v.object_id for v in ligadas} == {str(m.pk) for m in mesa.produto.midias.all()}


def test_importar_poe_a_foto_na_variacao_que_a_usa_na_loja(mesa):
    azul = VarianteProduto.objects.create(produto=mesa.produto, titulo="Azul", posicao=1)
    pv = "gid://shopify/ProductVariant/2"
    ExternalReference.objects.create(platform="shopify", entity_type="variantes",
                                     object_id=str(azul.pk), external_id=pv)
    foto(azul, 9)
    puxar(mesa.produto, 1, 2, das_variantes={pv: 2})
    assert [m.url for m in azul.midias.all()] == ["/media/produtos/2.png"]
    assert [m.url for m in mesa.variante.midias.all()] == ["/media/produtos/1.png"]


def test_importar_traz_de_volta_a_apagada_no_hub(mesa):
    """No Sincronizar a loja manda: a marca de apagada nao vale."""
    da_loja(mesa.variante, 1).delete()
    puxar(mesa.produto, 1)
    assert urls(mesa.produto) == ["/media/produtos/1.png"]
    assert "apagada_no_hub" not in ExternalReference.objects.get(external_id=gid(1)).metadata


def test_importar_de_novo_nao_acumula_arquivos(mesa):
    puxar(mesa.produto, 1, 2)
    arquivos = default_storage.listdir("produtos")[1]
    puxar(mesa.produto, 1, 2)
    assert sorted(default_storage.listdir("produtos")[1]) == sorted(arquivos)
    assert len(urls(mesa.produto)) == 2


@pytest.mark.parametrize("caso", [
    {"fotos": ()}, {"fotos": (1, 2), "falha": True}, {"fotos": (1,), "status": "PROCESSING"}])
def test_importar_sem_as_fotos_da_loja_mantem_as_do_hub(mesa, caso):
    foto(mesa.variante, 8)
    puxar(mesa.produto, *caso.pop("fotos"), **caso)
    assert urls(mesa.produto) == ["/media/8.png"]


def test_importar_mantem_o_vinculo_da_mesma_foto_com_outra_loja(mesa):
    """Sem isso o proximo envio ao WooCommerce mandaria a foto outra vez."""
    puxar(mesa.produto, 1)
    antiga = mesa.produto.midias.get()
    ExternalReference.objects.create(platform="woocommerce", entity_type="midias",
                                     object_id=str(antiga.pk), external_id="31")
    puxar(mesa.produto, 1)
    nova = mesa.produto.midias.get()
    assert nova.pk != antiga.pk
    assert ExternalReference.objects.get(external_id="31").object_id == str(nova.pk)


class Enviador:
    configuracao = SimpleNamespace(url_webhook="https://hub.test/webhook")

    def __init__(self, *na_loja, prontas=True):
        self.na_loja, self.prontas, self.apagadas, self.enviadas = list(na_loja), prontas, [], []
        self.cliente = self

    def graphql(self, query, _variaveis):
        if "fotosAgora" in query:
            return {"product": {"fotosAgora": {"nodes": [{"id": gid(n)} for n in self.na_loja]}}}
        return {"nodes": [{"id": i, "status": "READY", "image": {"url": cdn(i[-2:])}}
                          for i in _variaveis["ids"]] if self.prontas else []}

    def mutacao(self, _query, variaveis, campo):
        if campo == "fileDelete":
            self.apagadas += variaveis["fileIds"]
            return {}
        self.enviadas = [m["originalSource"] for m in variaveis["media"]]
        ids = [*self.na_loja, *range(70, 70 + len(self.enviadas))]
        return {"product": {"media": {"nodes": [{"id": gid(n)} for n in ids]}}}


@pytest.fixture(autouse=True)
def _sem_espera(monkeypatch):
    monkeypatch.setattr(exportar, "ESPERA", 0)


def test_exportar_apaga_todas_da_loja_e_manda_as_do_hub(mesa):
    """A 5 foi cadastrada direto na loja, sem vinculo: tambem sai."""
    da_loja(mesa.variante, 1), foto(mesa.variante, 2)
    enviador = Enviador(1, 5)

    exportar.refazer(enviador, mesa.produto, PRODUTO)

    assert enviador.enviadas == ["https://hub.test/media/1.png", "https://hub.test/media/2.png"]
    assert enviador.apagadas == [gid(1), gid(5)]
    vivas = ExternalReference.objects.filter(entity_type="midias").exclude(object_id="")
    assert sorted(v.external_id for v in vivas) == [gid(70), gid(71)]
    assert {v.object_id for v in vivas} == {str(m.pk) for m in mesa.produto.midias.all()}


def test_webhook_atrasado_da_exportacao_nao_traz_nem_apaga(mesa):
    da_loja(mesa.variante, 1)
    exportar.refazer(Enviador(1), mesa.produto, PRODUTO)
    loja = Loja(70)
    loja.webhook(mesa.produto, 1)
    loja.webhook(mesa.produto, 70)
    assert urls(mesa.produto) == ["/media/1.png"] and loja.baixadas == []


def test_exportar_que_nao_processa_desfaz_e_mantem_as_da_loja(mesa):
    """URL do hub fora do ar: apagar antes deixava o produto sem foto na loja."""
    da_loja(mesa.variante, 1)
    enviador = Enviador(1, prontas=False)
    with pytest.raises(ShopifyErro, match="mantidas"):
        exportar.refazer(enviador, mesa.produto, PRODUTO)
    assert enviador.apagadas == [gid(70)]
    viva = ExternalReference.objects.exclude(object_id="").get(entity_type="midias")
    assert viva.external_id == gid(1)


def test_exportar_sem_foto_no_hub_nao_apaga_as_da_loja(mesa):
    enviador = Enviador(1)
    exportar.refazer(enviador, mesa.produto, PRODUTO)
    assert enviador.apagadas == [] and enviador.enviadas == []


@pytest.mark.parametrize("sincronizar", [True, False])
def test_so_o_sincronizar_refaz_as_fotos_no_update(conta, mesa, sincronizar):
    """Salvar o produto no hub segue pela referencia: reenviar tudo a cada edicao nao."""
    foto(mesa.variante, 1, enviado_src="/media/1.png")
    _vincular_variante(mesa.variante)
    enviador = _enviador(conta, _respostas_update(1))
    enviador.marketplace.refazer_fotos = sincronizar
    with patch.object(exportar, "refazer") as refazer:
        enviador.atualizar(mesa.produto, PRODUTO_GID)
    assert refazer.called is sincronizar


def test_exportar_dados_liga_o_refazer(conta):
    from apps.integracoes import exportar as exportador

    vistos = []
    anotar = patch.object(exportador, "_enviar",
                          side_effect=lambda loja, *_: vistos.append(loja.refazer_fotos))
    with (patch.object(exportador, "_registros", return_value=["1"]),
          patch.object(exportador, "_vinculados", return_value=set()), anotar):
        exportador.exportar_dados(
            SimpleNamespace(plataforma="shopify", account_id=conta.pk), ["produtos"],
            lambda *_: None)
    assert vistos == [True]
