"""Avaliacao do hub -> metaobject avaliacao_produto e media do produto na loja."""

import json
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.models import ExternalReference
from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Avaliacao, Cliente
from apps.loja.services.avaliacoes import criar_avaliacao
from apps.loja.services.variantes import criar_produto
from apps.shopify.cliente import ShopifyErro
from apps.shopify.envio.marketplace import ShopifyMarketplace
from apps.shopify.tests.avaliacoes_falsa import LojaFalsa

PRODUTO_GID = "gid://shopify/Product/55"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def cenario(conta):
    matriz = permissoes.matriz_vazia()
    matriz["enviar"]["avaliacoes"] = {"get": False, "create": True, "update": True,
                                      "delete": True}
    config = ConfiguracaoIntegracao.objects.create(
        account=conta, permissoes=matriz, url_webhook="https://hub.test/integracoes/x"
    )
    produto = criar_produto("Poltrona", sku="POL-1", price=Decimal("10.00"))
    ExternalReference.objects.create(platform="shopify", entity_type="produtos",
                                     object_id=str(produto.pk), external_id=PRODUTO_GID)
    loja = LojaFalsa()
    enviador = ShopifyMarketplace(config).enviador("avaliacoes")
    enviador._cliente = loja
    return enviador, loja, produto


def _avaliacao(produto, email="ana@x.com", nota=5, status="aprovada", fotos=()):
    cliente = Cliente.objects.create(email=email, nome="Ana", sobrenome="Lima")
    avaliacao = criar_avaliacao(cliente=cliente, produto=produto, nota=nota,
                                comentario="Boa", fotos=fotos)
    Avaliacao.objects.filter(pk=avaliacao.pk).update(status=status)
    return Avaliacao.objects.get(pk=avaliacao.pk)


def _metafields(loja):
    return {m["key"]: m["value"] for m in loja.ultima("metafieldsSet")["metafields"]}


def test_pendente_nao_vai_para_a_loja(cenario):
    """Publicar antes da moderacao poria texto ofensivo na vitrine."""
    enviador, loja, produto = cenario
    resultado = enviador.enviar("create", _avaliacao(produto, status="pendente").pk)
    assert resultado.startswith("ignorado")
    assert loja.chamadas == []


def test_aprovada_vira_metaobject_com_fotos_e_media_no_produto(cenario):
    enviador, loja, produto = cenario
    foto = SimpleUploadedFile("a.png", PNG, content_type="image/png")
    avaliacao = _avaliacao(produto, fotos=[foto])

    assert enviador.enviar("update", avaliacao.pk).startswith("publicada")

    upsert = loja.ultima("metaobjectUpsert")
    assert upsert["handle"] == {"type": "avaliacao_produto",
                                "handle": f"avaliacao-{avaliacao.uuid}"}
    campos = {c["key"]: c["value"] for c in upsert["metaobject"]["fields"]}
    assert campos["product"] == PRODUTO_GID and campos["rating"] == "5"
    assert campos["author"] == "Ana L." and campos["verified"] == "false"
    assert json.loads(campos["photos"]) == ["gid://shopify/MediaImage/1"]
    assert loja.ultima("fileCreate")["files"][0]["originalSource"].startswith("https://hub.test/")
    assert _metafields(loja)["review_count"] == "1"
    assert _metafields(loja)["rating_value"] == "5.0"
    assert Avaliacao.objects.get(pk=avaliacao.pk).publicada_em is not None


def test_reenvio_atualiza_o_mesmo_metaobject_sem_reenviar_fotos(cenario):
    """Retry do Celery criando outro metaobject duplicaria a avaliacao na vitrine."""
    enviador, loja, produto = cenario
    foto = SimpleUploadedFile("a.png", PNG, content_type="image/png")
    avaliacao = _avaliacao(produto, fotos=[foto])
    enviador.enviar("update", avaliacao.pk)
    enviador.enviar("update", avaliacao.pk)
    assert loja.nomes().count("fileCreate") == 1
    handles = {v["handle"]["handle"] for n, v in loja.chamadas if n == "metaobjectUpsert"}
    assert handles == {f"avaliacao-{avaliacao.uuid}"}
    assert ExternalReference.objects.filter(entity_type="avaliacoes").count() == 1


def test_media_conta_so_as_aprovadas_publicadas_e_arredonda(cenario):
    """4,5 + 4 + pendente 1: a pendente puxaria a media para baixo sem estar na loja."""
    enviador, loja, produto = cenario
    for email, nota in (("a@x.com", 5), ("b@x.com", 4), ("c@x.com", 4)):
        enviador.enviar("update", _avaliacao(produto, email=email, nota=nota).pk)
    enviador.enviar("create", _avaliacao(produto, email="d@x.com", nota=1, status="pendente").pk)
    valores = _metafields(loja)
    assert valores["review_count"] == "3"
    assert valores["rating_value"] == "4.3"
    assert len(json.loads(valores["reviews"])) == 3


def test_rejeitar_publicada_tira_da_loja_com_fotos_e_recalcula(cenario):
    enviador, loja, produto = cenario
    foto = SimpleUploadedFile("a.png", PNG, content_type="image/png")
    avaliacao = _avaliacao(produto, fotos=[foto])
    enviador.enviar("update", avaliacao.pk)
    Avaliacao.objects.filter(pk=avaliacao.pk).update(status="rejeitada")

    assert enviador.enviar("update", avaliacao.pk) == "retirada da loja"

    assert loja.ultima("metaobjectDelete")["id"].endswith(f"avaliacao-{avaliacao.uuid}")
    assert loja.ultima("fileDelete")["fileIds"] == ["gid://shopify/MediaImage/1"]
    # Sem nenhuma aprovada, os metafields saem: "0 avaliacoes" com media 0 nao vai.
    assert {m["key"] for m in loja.ultima("metafieldsDelete")["metafields"]} == {
        "reviews", "rating_value", "review_count"}
    assert not ExternalReference.objects.filter(entity_type__in=["avaliacoes",
                                                                 "foto_avaliacao"]).exists()
    assert Avaliacao.objects.get(pk=avaliacao.pk).publicada_em is None


def test_excluir_no_hub_tira_da_loja(cenario):
    enviador, loja, produto = cenario
    avaliacao = _avaliacao(produto)
    enviador.enviar("update", avaliacao.pk)
    pk = avaliacao.pk
    avaliacao.delete()
    assert enviador.enviar("delete", pk) == "excluido"
    assert "metaobjectDelete" in loja.nomes()


def test_cria_as_definicoes_quando_a_loja_nao_tem(cenario):
    """Sem a definicao o upsert falha e sem a do metafield a lista nao aceita referencias."""
    enviador, loja, produto = cenario
    loja.definicoes_existem = False
    enviador.enviar("update", _avaliacao(produto).pk)
    criadas = [v["definition"]["key"] for n, v in loja.chamadas if n == "metafieldDefinitionCreate"]
    assert "metaobjectDefinitionCreate" in loja.nomes()
    assert criadas == ["reviews", "rating_value", "review_count"]
    lista = next(v for n, v in loja.chamadas if n == "metafieldDefinitionCreate")
    assert lista["definition"]["validations"] == [
        {"name": "metaobject_definition_id", "value": "gid://def/1"}]


def test_produto_sem_vinculo_na_loja_falha_com_instrucao(cenario):
    enviador, _, produto = cenario
    ExternalReference.objects.filter(entity_type="produtos").delete()
    with pytest.raises(ShopifyErro, match="sincronize os produtos"):
        enviador.enviar("update", _avaliacao(produto).pk)


def test_fotos_sem_url_publica_do_hub_falham_com_instrucao(cenario):
    """/media/... local a Shopify nao baixa: a foto sumiria da avaliacao em silencio."""
    enviador, _, produto = cenario
    enviador.configuracao.url_webhook = ""
    foto = SimpleUploadedFile("a.png", PNG, content_type="image/png")
    with pytest.raises(ShopifyErro, match="URL"):
        enviador.enviar("update", _avaliacao(produto, fotos=[foto]).pk)


def test_aprovacao_sem_criar_ligado_e_ignorada(cenario):
    enviador, loja, produto = cenario
    enviador.configuracao.permissoes["enviar"]["avaliacoes"]["create"] = False
    resultado = enviador.enviar("update", _avaliacao(produto).pk)
    assert "Criar" in resultado
    assert loja.chamadas == []


def test_rejeitada_cuja_retirada_falhou_nao_entra_na_media_de_outra(cenario):
    """A retirada pode falhar (loja fora do ar); a proxima publicacao nao pode conta-la."""
    enviador, loja, produto = cenario
    rejeitada = _avaliacao(produto, email="a@x.com", nota=1)
    enviador.enviar("update", rejeitada.pk)
    Avaliacao.objects.filter(pk=rejeitada.pk).update(status="rejeitada")

    enviador.enviar("update", _avaliacao(produto, email="b@x.com", nota=5).pk)

    assert _metafields(loja)["review_count"] == "1"
    assert _metafields(loja)["rating_value"] == "5.0"
