"""Categoria de servico no Suri: um atributo por categoria, um servico de cada.

    Camiseta (Azul, Verde) + Instalacao (Simples, Completa) + Impermeabilizacao (Imper)
    -> Cor | Instalação: Sem serviço, Completa, Simples | Impermeabilização: Sem serviço,
       Imper; uma dimension por servico, com o SKU dele

Toda categoria comeca em "Sem serviço" (o Suri marca a primeira opcao): a dimension
das cores e a dos servicos das outras categorias precisam de um valor nela.
"""

from decimal import Decimal

import pytest

from apps.loja.models import CategoriaServico, RegraServico, Servico
from apps.suri.contexto import usando_configuracao
from apps.suri.importar_catalogo import importar_produto
from apps.suri.tests.loja_falsa import produto
from apps.suri.tests.test_servicos_dimensoes import _enviar, camiseta, cfg  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def servicos(camiseta):  # noqa: F811
    instalacao = CategoriaServico.objects.create(nome="Instalação", ordem=1)
    imper = CategoriaServico.objects.create(nome="Impermeabilização", ordem=2)
    criados = {}
    # Imper primeiro de proposito: a ordem dos atributos e a das categorias.
    for nome, sku, preco, categoria in (("Imper", "IMP", "30.00", imper),
                                        ("Simples", "INS1", "20.00", instalacao),
                                        ("Completa", "INS2", "40.00", instalacao)):
        servico = Servico.objects.create(nome=nome, sku=sku, preco=Decimal(preco),
                                         categoria=categoria)
        RegraServico.objects.create(servico=servico,
                                    tipo=RegraServico.Tipo.PRODUTO).produtos.set([camiseta])
        criados[sku] = servico
    return criados


def test_cada_categoria_vira_um_atributo_e_cada_servico_uma_dimension_com_o_sku_dele(
        cfg, monkeypatch, camiseta, servicos):  # noqa: F811
    _, corpo = _enviar(cfg, monkeypatch, camiseta)

    assert corpo["attributes"] == [
        {"name": "Cor", "options": [{"name": "Azul"}, {"name": "Verde"}]},
        {"name": "Instalação", "options": [{"name": "Sem serviço"},
                                           {"name": "Completa (R$ 40,00)"},
                                           {"name": "Simples (R$ 20,00)"}]},
        {"name": "Impermeabilização", "options": [{"name": "Sem serviço"},
                                                  {"name": "Imper (R$ 30,00)"}]}]
    por_sku = {d["sku"]: d for d in corpo["dimensions"]}
    assert list(por_sku) == ["CAM-AZ", "CAM-VD", "INS2", "INS1", "IMP"]
    assert por_sku["INS1"]["dimensions"] == {
        "Cor": "Azul", "Instalação": "Simples (R$ 20,00)", "Impermeabilização": "Sem serviço"}
    assert por_sku["INS1"]["price"] == por_sku["CAM-AZ"]["price"] + Decimal("20.00")
    assert not any("Qualquer" in d["dimensions"].values() for d in corpo["dimensions"])


def test_catalogo_do_suri_nao_transforma_atributo_de_categoria_em_opcao(cfg, servicos):  # noqa: F811
    dados = produto()
    dados["attributes"] = [*dados["attributes"], {"name": "Impermeabilização", "options": [
        {"name": "Sem serviço"}, {"name": "Imper (R$ 30,00)"}]}]
    for dimensao in dados["dimensions"]:
        dimensao["dimensions"] = {**dimensao["dimensions"], "Impermeabilização": "Sem serviço"}

    with usando_configuracao(cfg):
        obj, _ = importar_produto(dados, sobrescrever=True)

    azul = obj.variantes.get(sku="CAM-AZ")
    assert [o.valor.tipo.nome for o in azul.opcoes.all()] == ["Cor"]


def test_renomear_a_categoria_reenvia_os_produtos_dos_servicos_dela(
        servicos, cfg, monkeypatch, camiseta, django_capture_on_commit_callbacks):  # noqa: F811
    """O nome da categoria e o nome do atributo no Suri: sem reenvio ficava o antigo.

    `servicos` antes de `cfg`: criados com o Suri ja configurado, deixariam um reenvio
    pendente (sem commit no teste) que absorveria o da categoria."""
    _enviar(cfg, monkeypatch, camiseta)
    enfileirados = []
    monkeypatch.setattr("apps.integracoes.envio.distribuidor._enfileirar",
                        lambda *args: enfileirados.append(args))
    categoria = servicos["IMP"].categoria

    with django_capture_on_commit_callbacks(execute=True):
        categoria.nome = "Proteção"
        categoria.save()

    assert {(r, o, pk) for _c, r, o, pk in enfileirados} == {("produtos", "update", camiseta.pk)}
