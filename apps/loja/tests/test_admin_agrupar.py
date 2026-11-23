"""Botao "Agrupar produtos simples" dentro do produto (admin/produtos_agrupar.py).

Trocar o tipo do simples para Variavel mostra a secao Variantes com o botao; o dialog
busca os outros simples, sugere nome e valores e posta em <pk>/agrupar/. O produto
aberto e o pai.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.core.models import ExternalReference, User
from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao
from apps.loja.models import Produto, VarianteProduto

pytestmark = pytest.mark.django_db


def _simples(nome, sku):
    produto = Produto.objects.create(nome=nome)
    variante = produto.variante_padrao
    variante.sku, variante.price, variante.inventory_quantity = sku, Decimal("49.90"), 2
    variante.save()
    return produto


@pytest.fixture
def camisetas():
    return [_simples("Camiseta Basica P", "CAM-P"), _simples("Camiseta Basica M", "CAM-M"),
            _simples("Camiseta Basica G", "CAM-G")]


def _url(produto, rota=""):
    return reverse(f"admin:loja_produto_agrupar{rota}", args=[produto.pk])


def _mensagens(resposta):
    return [str(m) for m in get_messages(resposta.wsgi_request)]


def _agrupar(cliente, pai, outros, valores, **extra):
    dados = {"produtos": [p.pk for p in outros], "nome": "Camiseta Basica", "opcao": "Tamanho",
             **{f"valor_{p.pk}": v for p, v in zip([pai, *outros], valores, strict=True)},
             **extra}
    return cliente.post(_url(pai), dados)


def test_produto_simples_tem_o_botao_e_o_dialog_na_secao_variantes(admin_logado, camisetas):
    """A secao so aparece com o tipo Variavel: trocar o tipo e o que libera o botao."""
    html = admin_logado.get(
        reverse("admin:loja_produto_change", args=[camisetas[0].pk])).content.decode()

    assert 'data-abrir-modal-etapas="modal-agrupar"' in html
    assert 'id="modal-agrupar"' in html
    assert f'action="{_url(camisetas[0])}"' in html
    # A busca ja abre pelo comeco do nome: as outras camisetas aparecem sem digitar.
    assert 'data-busca-inicial="Camiseta Basica"' in html


def test_produto_variavel_nao_tem_o_botao(admin_logado):
    variavel = Produto.objects.create(nome="Calca", tipo=Produto.Tipo.VARIAVEL)

    html = admin_logado.get(reverse("admin:loja_produto_change", args=[variavel.pk])).content

    assert b'modal-agrupar' not in html


def test_busca_traz_so_os_outros_simples_pelo_nome_ou_sku(admin_logado, camisetas):
    variavel = Produto.objects.create(nome="Camiseta Variavel", tipo=Produto.Tipo.VARIAVEL)
    VarianteProduto.objects.create(produto=variavel, sku="CAM-V")

    por_nome = admin_logado.get(_url(camisetas[0], "_buscar"), {"q": "camiseta"}).json()
    por_sku = admin_logado.get(_url(camisetas[0], "_buscar"), {"q": "cam-g"}).json()

    assert [p["sku"] for p in por_nome["produtos"]] == ["CAM-M", "CAM-G"]
    assert por_nome["produtos"][0] == {"id": camisetas[1].pk, "nome": "Camiseta Basica M",
                                       "sku": "CAM-M", "preco": "49.90", "estoque": 2}
    assert [p["id"] for p in por_sku["produtos"]] == [camisetas[2].pk]


def test_sugestao_vem_com_o_pai_primeiro(admin_logado, camisetas):
    pai, m, g = camisetas

    dados = admin_logado.get(_url(pai, "_sugestao"), {"ids": f"{g.pk},{m.pk}"}).json()

    assert dados["nome"] == "Camiseta Basica"
    assert dados["itens"] == [
        {"id": pai.pk, "nome": pai.nome, "sku": "CAM-P", "valor": "P"},
        {"id": m.pk, "nome": m.nome, "sku": "CAM-M", "valor": "M"},
        {"id": g.pk, "nome": g.nome, "sku": "CAM-G", "valor": "G"},
    ]


def test_confirmar_agrupa_no_produto_aberto_e_volta_para_ele(admin_logado, camisetas):
    pai, m, g = camisetas

    resposta = _agrupar(admin_logado, pai, [m, g], ["P", "M", "G"])

    assert resposta.status_code == 302
    assert resposta.url == reverse("admin:loja_produto_change", args=[pai.pk])
    pai.refresh_from_db()
    assert pai.tipo == Produto.Tipo.VARIAVEL
    assert sorted(pai.variantes.values_list("sku", flat=True)) == ["CAM-G", "CAM-M", "CAM-P"]
    assert any("3 produtos agrupados" in m for m in _mensagens(resposta))


def test_erro_volta_para_o_produto_com_o_que_corrigir_e_nada_muda(admin_logado, camisetas):
    pai, m, _g = camisetas

    resposta = _agrupar(admin_logado, pai, [m], ["P", "p"])

    assert resposta.url == reverse("admin:loja_produto_change", args=[pai.pk])
    assert any("repetido" in m for m in _mensagens(resposta))
    assert Produto.objects.filter(tipo=Produto.Tipo.SIMPLES).count() == 3


def test_loja_com_excluir_desligado_avisa_que_o_antigo_fica_la(admin_logado, camisetas, conta):
    """Sem o aviso a loja fica com o simples antigo e a variante nova, SKU duplicado."""
    pai, m, _g = camisetas
    ConfiguracaoIntegracao.objects.create(account=conta, nome="Loja Shopify", plataforma="shopify",
                                          permissoes=permissoes.matriz_vazia())
    ExternalReference.objects.create(platform="shopify", entity_type="produtos",
                                     object_id=str(m.pk), external_id="P/2")

    resposta = _agrupar(admin_logado, pai, [m], ["P", "M"])

    assert any("Loja Shopify" in t and "Excluir esta desligado" in t
               for t in _mensagens(resposta))


def test_sem_permissao_de_excluir_nao_agrupa(client, conta, camisetas):
    """Agrupar exclui os simples: so altera quem tambem pode excluir produto."""
    usuario = User.objects.create_user("op", "op@x.test", "senha-forte-123", account=conta,
                                       is_staff=True)
    usuario.user_permissions.add(*Permission.objects.filter(
        codename__in=["view_produto", "change_produto"]))
    client.force_login(usuario)
    pai, m, _g = camisetas

    assert _agrupar(client, pai, [m], ["P", "M"]).status_code == 403
    assert client.get(_url(pai, "_buscar"), {"q": "cam"}).status_code == 403
    assert Produto.objects.filter(tipo=Produto.Tipo.SIMPLES).count() == 3
