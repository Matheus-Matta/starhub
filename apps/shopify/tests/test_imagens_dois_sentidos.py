"""Fotos nos dois sentidos pela referencia: apagar de um lado apaga do outro, sem laco."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import MidiaProduto, VarianteProduto
from apps.loja.services.midias import imagens_da_variante, sincronizar_midias
from apps.loja.services.variantes import criar_produto
from apps.shopify.imagens import sincronizar_imagens

pytestmark = pytest.mark.django_db
PRODUTO = "gid://shopify/Product/9"


def gid(n):
    return f"gid://shopify/MediaImage/{n}"


def cdn(n):
    return f"https://cdn.shopify.com/s/files/1/{n}.png"


def foto(variante, n, **metadata):
    midia = MidiaProduto.objects.create(produto=variante.produto, variante=variante,
                                        url=f"/media/{n}.png", posicao=n)
    if metadata:
        ExternalReference.objects.create(platform="shopify", entity_type="midias",
                                         object_id=str(midia.pk), external_id=gid(n),
                                         metadata=metadata)
    return midia


def da_loja(variante, n):
    return foto(variante, n, shopify_src=cdn(n))


class Loja:
    """A loja de verdade agora (`fotos`) e a lista que o webhook trouxe (talvez velha)."""

    def __init__(self, *fotos):
        self.fotos, self.baixadas = fotos, []

    def graphql(self, _query, _variaveis):
        return {"product": {"fotosAgora": {"nodes": [{"id": gid(n)} for n in self.fotos]}}}

    def webhook(self, produto, *lista, url=cdn, cortada=False):
        def baixar(origem, **_):
            self.baixadas.append(origem)
            return f"/media/baixada-{len(self.baixadas)}.png"

        dados = {"id": PRODUTO, "media": {
            "nodes": [{"id": gid(n), "alt": f"alt {n}", "image": {"url": url(n)}}
                      for n in lista], "pageInfo": {"hasNextPage": cortada}}}
        with patch("apps.shopify.imagens_gravar._baixar", side_effect=baixar), \
                patch("apps.shopify.midias.cliente_da_loja", return_value=self):
            sincronizar_imagens(produto, dados)


def urls(produto):
    return list(produto.midias.order_by("pk").values_list("url", flat=True))


@pytest.fixture(name="mesa")
def mesa_na_loja(conta, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    produto = criar_produto("Mesa", sku="M1")
    ExternalReference.objects.create(platform="shopify", entity_type="produtos",
                                     object_id=str(produto.pk), external_id=PRODUTO)
    return SimpleNamespace(produto=produto, variante=produto.variante_padrao)


def apagar_no_hub(variante, midia):
    with patch("apps.integracoes.envio.distribuidor.Distribuidor.distribuir") as enviar:
        sincronizar_midias(variante, [i for i in imagens_da_variante(variante)
                                      if i["id"] != midia.pk])
    return enviar


def test_apagada_na_loja_sai_do_hub_e_nao_gera_envio_de_volta(mesa):
    da_loja(mesa.variante, 1), da_loja(mesa.variante, 2)
    with patch("apps.integracoes.envio.distribuidor.Distribuidor.distribuir") as enviar:
        Loja(1).webhook(mesa.produto, 1)
    assert urls(mesa.produto) == ["/media/1.png"]
    assert not enviar.called, "hub -> loja -> hub nao pode virar laco"
    assert not ExternalReference.objects.filter(external_id=gid(2)).exists()


def test_apagada_no_hub_gera_envio_e_o_webhook_atrasado_nao_a_traz_de_volta(mesa):
    """O webhook do proprio update chega antes do fileDelete, com a foto na lista."""
    midia = da_loja(mesa.variante, 1)
    da_loja(mesa.variante, 2)

    enviar = apagar_no_hub(mesa.variante, midia)
    loja = Loja(1, 2)
    loja.webhook(mesa.produto, 1, 2)

    assert enviar.called
    assert urls(mesa.produto) == ["/media/2.png"] and loja.baixadas == []


def test_webhook_de_antes_do_file_delete_processado_depois_nao_traz_a_foto(mesa):
    """A lista veio com a foto, e quando a tarefa rodou a loja ja a tinha apagado."""
    da_loja(mesa.variante, 2)
    loja = Loja(2)
    loja.webhook(mesa.produto, 1, 2)
    assert urls(mesa.produto) == ["/media/2.png"] and loja.baixadas == []


def test_webhook_velho_nao_apaga_a_foto_que_o_hub_acabou_de_mandar(mesa):
    da_loja(mesa.variante, 1)
    foto(mesa.variante, 2, enviado_src="/media/2.png", shopify_src=cdn(2))
    Loja(1, 2).webhook(mesa.produto, 1)
    assert urls(mesa.produto) == ["/media/1.png", "/media/2.png"]


def test_nova_no_hub_ainda_nao_enviada_fica(mesa):
    da_loja(mesa.variante, 1)
    foto(mesa.variante, 2)
    Loja(1).webhook(mesa.produto, 1)
    assert urls(mesa.produto) == ["/media/1.png", "/media/2.png"]


def test_enviada_que_falhou_na_loja_nao_some_do_hub(mesa):
    """Nunca ficou pronta la: existe so no hub."""
    foto(mesa.variante, 2, enviado_src="/media/2.png")
    Loja().webhook(mesa.produto)
    assert urls(mesa.produto) == ["/media/2.png"]


def test_lista_cortada_confere_na_loja_antes_de_apagar(mesa):
    """Produto com mais fotos que a consulta traz: faltar na lista nao e ter saido."""
    da_loja(mesa.variante, 1), da_loja(mesa.variante, 2)
    Loja(1, 2).webhook(mesa.produto, 1, cortada=True)
    assert len(urls(mesa.produto)) == 2


def test_produto_do_hub_ligado_a_dois_da_loja_nao_apaga(mesa):
    """A lista de um produto da loja nao tem as fotos do outro."""
    ExternalReference.objects.create(platform="shopify", entity_type="produtos",
                                     object_id=str(mesa.produto.pk),
                                     external_id="gid://shopify/Product/10")
    da_loja(mesa.variante, 1)
    Loja().webhook(mesa.produto)
    assert urls(mesa.produto) == ["/media/1.png"]


def test_repetida_na_loja_so_sai_do_hub_quando_as_duas_saem(mesa):
    midia = da_loja(mesa.variante, 1)
    ExternalReference.objects.create(platform="shopify", entity_type="midias",
                                     object_id=str(midia.pk), external_id=gid(2),
                                     metadata={"shopify_src": cdn(2)})
    Loja(2).webhook(mesa.produto, 2)
    assert urls(mesa.produto) == ["/media/1.png"]
    Loja().webhook(mesa.produto)
    assert urls(mesa.produto) == []


def test_apagar_a_copia_de_uma_variacao_nao_apaga_a_foto_na_loja(mesa):
    """A mesma foto em duas variacoes e uma so na loja: o vinculo passa para a que ficou."""
    azul = VarianteProduto.objects.create(produto=mesa.produto, titulo="Azul", posicao=1)
    midia = da_loja(mesa.variante, 1)
    copia = MidiaProduto.objects.create(produto=mesa.produto, variante=azul, url=midia.url)

    apagar_no_hub(mesa.variante, midia)

    vinculo = ExternalReference.objects.get(external_id=gid(1))
    assert vinculo.object_id == str(copia.pk) and "apagada_no_hub" not in vinculo.metadata


def test_foto_trocada_no_hub_vira_outra_e_a_antiga_fica_marcada(mesa):
    """Foto que veio da loja, trocada no hub na mesma linha: a nova nunca subia."""
    midia = da_loja(mesa.variante, 1)
    with patch("apps.integracoes.envio.distribuidor.Distribuidor.distribuir"):
        sincronizar_midias(mesa.variante, [{"id": midia.pk, "src": "/media/nova.png"}])
    assert mesa.produto.midias.get().pk != midia.pk
    assert ExternalReference.objects.get(external_id=gid(1)).metadata["apagada_no_hub"]
