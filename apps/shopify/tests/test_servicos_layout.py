"""Layout dos servicos no tema Shopify e pares de escolha exclusiva."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core.models import ExternalReference
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import RegraServico, Servico
from apps.shopify.models import ApresentacaoServicoShopify
from apps.shopify.tests import test_servicos_shopify as base

ORIGEM = base.ORIGEM
_exportar = base._exportar
_sem_rede = base._sem_rede
cfg = base.cfg
montagem = base.montagem
sofa = base.sofa

pytestmark = pytest.mark.django_db


def _garantia(sofa, com_regra=True, nome="Garantia estendida", sku="SERV-GAR",
              variante=803):
    servico = Servico.objects.create(nome=nome, sku=sku, preco=Decimal("50.00"))
    if com_regra:
        regra = RegraServico.objects.create(
            servico=servico, tipo=RegraServico.Tipo.PRODUTO, preco=Decimal("50.00"))
        regra.produtos.set([sofa])
        ExternalReference.objects.create(
            platform="shopify", entity_type="servicos_variantes",
            external_id=f"gid://shopify/ProductVariant/{variante}", object_id=str(servico.pk),
            external_parent_id="gid://shopify/Product/703", metadata={"preco": "50.00"},
        )
    return servico


@pytest.mark.parametrize("tipo", ["radio", "select", "cards"])
def test_campo_agrupa_varios_servicos_quando_todos_valem_para_o_produto(
        client, cfg, sofa, montagem, tipo):
    _exportar(cfg, montagem)
    garantia = _garantia(sofa)
    seguro = _garantia(sofa, nome="Seguro contra danos", sku="SERV-SEG", variante=804)
    apresentacao = ApresentacaoServicoShopify.objects.create(
        servico=montagem, tipo_campo=tipo,
        titulo_grupo="Escolha a protecao", obrigatorio=True,
        padrao=ApresentacaoServicoShopify.Padrao.ALTERNATIVO, ordem=5,
    )
    apresentacao.servicos_vinculados.set([garantia, seguro])

    resposta = client.get(reverse("shopify_servicos_publico", args=[cfg.uuid]),
                          {"produto": "111"}, headers={"Origin": ORIGEM}).json()

    por_id = {item["id"]: item for item in resposta["servicos"]}
    principal, alternativo = por_id[montagem.pk], por_id[garantia.pk]
    assert {item["grupo"] for item in por_id.values()} == {f"servicos-{apresentacao.pk}"}
    assert {item["tipo_campo"] for item in por_id.values()} == {tipo}
    assert principal["titulo_grupo"] == "Escolha a protecao"
    assert principal["obrigatorio"] is True
    assert principal["selecionado"] is False and alternativo["selecionado"] is True
    assert [item["id"] for item in resposta["servicos"]] == [
        montagem.pk, garantia.pk, seguro.pk]


def test_radio_vira_checkbox_se_o_produto_nao_tiver_o_servico_vinculado(
        client, cfg, sofa, montagem):
    _exportar(cfg, montagem)
    garantia = _garantia(sofa, com_regra=False)
    apresentacao = ApresentacaoServicoShopify.objects.create(
        servico=montagem, tipo_campo=ApresentacaoServicoShopify.TipoCampo.RADIO,
        obrigatorio=True,
    )
    apresentacao.servicos_vinculados.set([garantia])

    servicos = client.get(reverse("shopify_servicos_publico", args=[cfg.uuid]),
                           {"produto": "111"}, headers={"Origin": ORIGEM}).json()["servicos"]

    assert len(servicos) == 1
    assert servicos[0]["tipo_campo"] == "checkbox"
    assert servicos[0]["grupo"] == "" and servicos[0]["obrigatorio"] is False


def test_radio_exige_outro_servico_e_nao_aceita_ele_mesmo(montagem):
    apresentacao = ApresentacaoServicoShopify.objects.create(
        servico=montagem, tipo_campo=ApresentacaoServicoShopify.TipoCampo.RADIO)

    with pytest.raises(ValidationError, match="servico vinculado"):
        apresentacao.validar_vinculados([])
    with pytest.raises(ValidationError, match="outro servico"):
        apresentacao.validar_vinculados([montagem])


def test_admin_exibe_configuracao_shopify_no_proprio_servico(admin_logado, cfg, montagem):
    html = admin_logado.get(
        reverse("admin:loja_servico_change", args=[montagem.pk])).content.decode()

    for campo in (
        "shopify_tipo_campo", "shopify_rotulo", "shopify_descricao", "shopify_ordem",
        "shopify_servicos_vinculados", "shopify_titulo_grupo", "shopify_obrigatorio",
        "shopify_padrao",
    ):
        assert f'name="{campo}"' in html
    assert "Checkbox" in html and "Radio" in html and "Lista" in html and "Cartoes" in html
    campo = html.split('name="shopify_servicos_vinculados"', 1)[1].split(">", 1)[0]
    assert "multiple" in campo
    assert html.rfind("Layout na Shopify") > html.rfind("Regras")


def test_admin_oculta_layout_sem_shopify_ativa(admin_logado, montagem):
    html = admin_logado.get(
        reverse("admin:loja_servico_change", args=[montagem.pk])).content.decode()

    assert "Layout na Shopify" not in html
    assert 'name="shopify_tipo_campo"' not in html


def test_admin_nao_altera_layout_oculto_ao_salvar_servico(admin_logado, montagem):
    layout = ApresentacaoServicoShopify.objects.create(
        servico=montagem, tipo_campo=ApresentacaoServicoShopify.TipoCampo.CARTOES,
        rotulo="Instalacao especial", ordem=4)

    resposta = admin_logado.post(
        reverse("admin:loja_servico_change", args=[montagem.pk]), {
            "nome": montagem.nome, "sku": montagem.sku, "preco": "130.00",
            "active": "on", "inclusao": "escolha", "_save": "1",
        })

    assert resposta.status_code == 302, resposta.content.decode()[:2000]
    layout.refresh_from_db()
    assert (layout.tipo_campo, layout.rotulo, layout.ordem) == (
        "cards", "Instalacao especial", 4)


def test_admin_oculta_layout_se_shopify_ainda_nao_foi_configurada(
        admin_logado, conta, montagem):
    ConfiguracaoIntegracao.objects.create(
        account=conta, plataforma=ConfiguracaoIntegracao.Plataforma.SHOPIFY,
        dominio_loja="")

    html = admin_logado.get(
        reverse("admin:loja_servico_change", args=[montagem.pk])).content.decode()

    assert "Layout na Shopify" not in html


def test_admin_salva_layout_dentro_do_cadastro_do_servico(
        admin_logado, cfg, montagem, sofa):
    garantia = _garantia(sofa)

    resposta = admin_logado.post(
        reverse("admin:loja_servico_change", args=[montagem.pk]), {
            "nome": montagem.nome, "sku": montagem.sku, "preco": "120.00",
            "active": "on", "inclusao": "escolha",
            "shopify_tipo_campo": "radio", "shopify_rotulo": "Instalacao",
            "shopify_descricao": "Feita por especialista", "shopify_ordem": "3",
            "shopify_servicos_vinculados": [garantia.pk],
            "shopify_titulo_grupo": "Escolha uma protecao",
            "shopify_obrigatorio": "on", "shopify_padrao": "principal", "_save": "1",
        })

    assert resposta.status_code == 302, resposta.content.decode()[:2000]
    layout = ApresentacaoServicoShopify.objects.get(servico=montagem)
    assert (layout.tipo_campo, list(layout.servicos_vinculados.all()),
            layout.rotulo, layout.ordem) == ("radio", [garantia], "Instalacao", 3)
