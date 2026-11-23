"""Agrupar produtos simples (o ERP so cadastra simples) num produto variavel.

O ERP manda P, M, G e GG como quatro simples. Recriar como variavel no admin perdia
o id das variantes (pedidos, vinculos com as lojas) e custava tempo. O agrupamento
move as variantes para o produto escolhido como pai, com o mesmo id, SKU, preco e
estoque, e exclui os simples que ficaram vazios.
"""

from decimal import Decimal

import pytest

from apps.core.models import ExternalReference
from apps.loja.models import (
    Cliente,
    Cupom,
    ItemPedido,
    MidiaProduto,
    Pedido,
    Produto,
    RegraServico,
    Servico,
    VarianteProduto,
)
from apps.loja.services.agrupar import AgrupamentoInvalido, agrupar, sugestao
from apps.loja.services.avaliacoes import criar_avaliacao

pytestmark = pytest.mark.django_db


def _simples(nome, sku, preco="10", estoque=1):
    produto = Produto.objects.create(nome=nome)
    variante = produto.variante_padrao
    variante.sku, variante.price, variante.inventory_quantity = sku, Decimal(preco), estoque
    variante.save()
    return produto


@pytest.fixture
def camisetas():
    return [
        _simples("Camiseta Basica P", "CAM-P", "49.90", 3),
        _simples("Camiseta Basica M", "CAM-M", "49.90", 0),
        _simples("Camiseta Basica G", "CAM-G", "54.90", 7),
        _simples("Camiseta Basica GG", "CAM-GG", "54.90", 2),
    ]


def _agrupar(produtos, base=None, valores=("P", "M", "G", "GG")):
    base = base or produtos[0]
    return agrupar(base.pk, [p.pk for p in produtos], "Camiseta Basica", "Tamanho",
                   {p.pk: v for p, v in zip(produtos, valores, strict=True)})


def test_quatro_simples_viram_um_variavel_com_as_mesmas_variantes(camisetas):
    """Variante recriada perderia o id: pedido, cupom e vinculo da loja apontam para ele."""
    antes = {p.variante_padrao.pk: (p.sku, p.preco_regular, p.estoque) for p in camisetas}

    pai = _agrupar(camisetas, base=camisetas[1])

    pai.refresh_from_db()
    assert pai.pk == camisetas[1].pk
    assert pai.tipo == Produto.Tipo.VARIAVEL and pai.nome == "Camiseta Basica"
    variantes = list(pai.variantes.order_by("posicao"))
    assert {v.pk: (v.sku, v.price, v.inventory_quantity) for v in variantes} == antes
    assert [v.titulo for v in variantes] == ["M", "P", "G", "GG"]
    assert [v.is_default for v in variantes] == [True, False, False, False]
    assert {(o.valor.tipo.nome, o.valor.valor) for v in variantes for o in v.opcoes.all()} == {
        ("Tamanho", "P"), ("Tamanho", "M"), ("Tamanho", "G"), ("Tamanho", "GG")}
    assert list(Produto.objects.values_list("pk", flat=True)) == [pai.pk]


def test_pedido_foto_avaliacao_cupom_e_servico_passam_para_o_pai(camisetas):
    """Produto excluido levaria junto foto e avaliacao, e o pedido perderia o produto."""
    outro = camisetas[2]
    variante = outro.variante_padrao
    pedido = Pedido.objects.create(total=Decimal("54.90"))
    item = ItemPedido.objects.create(pedido=pedido, produto=outro, variante=variante,
                                     nome="Camiseta Basica G")
    foto = MidiaProduto.objects.create(produto=outro, url="https://cdn.test/g.jpg")
    cliente = Cliente.objects.create(email="ana@x.com", nome="Ana")
    avaliacao = criar_avaliacao(cliente=cliente, produto=outro, nota=5, comentario="Boa")
    cupom = Cupom.objects.create(name="DEZ", discount_type=Cupom.TipoDesconto.PERCENTUAL,
                                 value=Decimal("10"))
    cupom.produtos.add(outro)
    servico = Servico.objects.create(nome="Montagem", sku="SERV-MONTAGEM")
    regra = RegraServico.objects.create(servico=servico, tipo=RegraServico.Tipo.PRODUTO)
    regra.produtos.add(outro)

    pai = _agrupar(camisetas)

    item.refresh_from_db()
    foto.refresh_from_db()
    avaliacao.refresh_from_db()
    assert (item.produto_id, item.variante_id) == (pai.pk, variante.pk)
    assert (foto.produto_id, foto.variante_id) == (pai.pk, variante.pk)
    assert avaliacao.produto_id == pai.pk
    assert list(cupom.produtos.all()) == [pai]
    assert list(regra.produtos.all()) == [pai]


def test_vinculo_das_variantes_movidas_sai_e_o_id_antigo_aponta_para_a_variante(camisetas):
    """A variante movida ligada a OUTRO produto da loja faria o update do pai falhar;
    o ERP continua mandando o id do simples antigo e precisa cair na variacao."""
    outro = camisetas[3]
    variante = outro.variante_padrao
    ExternalReference.objects.create(platform="shopify", entity_type="variantes",
                                     object_id=str(variante.pk), external_id="PV/44")
    ExternalReference.objects.create(platform="shopify", entity_type="produtos",
                                     object_id=str(outro.pk), external_id="P/4")
    foto = MidiaProduto.objects.create(produto=outro, url="https://cdn.test/gg.jpg")
    ExternalReference.objects.create(platform="shopify", entity_type="midias",
                                     object_id=str(foto.pk), external_id="M/4")

    _agrupar(camisetas)

    assert not ExternalReference.objects.filter(entity_type__in=["variantes", "midias"]).exists()
    # O do produto fica: e por ele que a exclusao chega a loja (envio depois do commit).
    assert ExternalReference.objects.filter(entity_type="produtos", external_id="P/4").exists()
    antigos = dict(ExternalReference.objects.filter(
        platform="api", entity_type="produto_agrupado").values_list("external_id", "object_id"))
    assert antigos == {str(p.pk): str(p.variante_padrao.pk) for p in camisetas[1:]}
    assert antigos[str(outro.pk)] == str(variante.pk)


@pytest.mark.parametrize("valores, trecho", [
    (("P", "p", "G", "GG"), "repetido"),
    (("P", "", "G", "GG"), "valor"),
])
def test_valor_vazio_ou_repetido_nao_agrupa(camisetas, valores, trecho):
    """Duas variantes com a mesma opcao ficam iguais na loja (o Shopify recusa)."""
    with pytest.raises(AgrupamentoInvalido, match=trecho):
        _agrupar(camisetas, valores=valores)
    assert Produto.objects.filter(tipo=Produto.Tipo.SIMPLES).count() == 4


def test_produto_que_nao_e_simples_nao_entra_e_nada_muda(camisetas):
    """Variavel ou bundle no grupo misturaria varias variantes sem opcao definida."""
    variavel = Produto.objects.create(nome="Camiseta Variavel", tipo=Produto.Tipo.VARIAVEL)
    VarianteProduto.objects.create(produto=variavel, sku="CV-1")
    grupo = [*camisetas[:3], variavel]

    with pytest.raises(AgrupamentoInvalido, match="Camiseta Variavel"):
        _agrupar(grupo)
    assert VarianteProduto.objects.get(sku="CAM-M").produto_id == camisetas[1].pk


def test_um_produto_so_nao_agrupa(camisetas):
    with pytest.raises(AgrupamentoInvalido, match="pelo menos dois"):
        agrupar(camisetas[0].pk, [camisetas[0].pk], "Camiseta", "Tamanho",
                {camisetas[0].pk: "P"})


def test_cliente_que_avaliou_dois_do_grupo_explica_o_que_fazer(camisetas):
    """A regra 1 avaliacao por cliente e produto e do banco: sem o aviso, erro 500."""
    cliente = Cliente.objects.create(email="bia@x.com", nome="Bia")
    for produto in camisetas[:2]:
        criar_avaliacao(cliente=cliente, produto=produto, nota=4, comentario="Ok")

    with pytest.raises(AgrupamentoInvalido, match="bia@x.com"):
        _agrupar(camisetas)


def test_sugestao_separa_o_nome_comum_do_que_muda_em_cada_um():
    """Digitar o nome e a opcao de cada produto e o tempo que o agrupamento economiza."""
    produtos = [Produto(pk=1, nome="SOFA TORONTO 2 LUGARES CINZA"),
                Produto(pk=2, nome="SOFA TORONTO 3 LUGARES CINZA")]

    assert sugestao(produtos) == ("SOFA TORONTO", {1: "2 LUGARES CINZA",
                                                   2: "3 LUGARES CINZA"})


def test_sugestao_com_nomes_iguais_deixa_o_valor_para_o_operador():
    produtos = [Produto(pk=1, nome="Mesa"), Produto(pk=2, nome="Mesa")]

    assert sugestao(produtos) == ("Mesa", {1: "", 2: ""})
