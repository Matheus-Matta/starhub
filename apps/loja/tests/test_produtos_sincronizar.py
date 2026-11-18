""""Sincronizar com integracao": acao em massa e botao do produto.

O dialog escolhe a integracao; vira uma tarefa de Exportar so com os produtos
escolhidos (dados e depois o estoque), sem precisar editar o produto para ele ir.
"""

import pytest
from django.urls import reverse

from apps.integracoes.envio import registro
from apps.integracoes.models import ExecucaoIntegracao
from apps.integracoes.tasks import exportar_dados
from apps.integracoes.tests.envio_falso import (
    MarketplaceFalso,
    ShopifyFalso,
    chamadas,
    configuracao,
    ligar,
)
from apps.loja.models import Produto

pytestmark = pytest.mark.django_db
LISTA = reverse("admin:loja_produto_changelist")


@pytest.fixture
def falsos():
    """Marketplaces sem rede no registro (o mesmo da fixture de apps/integracoes)."""
    antes = dict(registro._classes)
    registro._classes.clear()
    registro.registrar(MarketplaceFalso)
    registro.registrar(ShopifyFalso)
    chamadas.clear()
    yield chamadas
    registro._classes.clear()
    registro._classes.update(antes)


def _produtos(*nomes):
    produtos = [Produto.objects.create(nome=nome) for nome in nomes]
    for produto in produtos:
        produto.variantes.update(manage_inventory=True, inventory_quantity=7)
    return produtos


def _execucao():
    return ExecucaoIntegracao.objects.get(tipo=ExecucaoIntegracao.Tipo.EXPORTAR)


def test_acao_em_massa_cria_a_tarefa_so_com_os_escolhidos(admin_logado, falsos):
    loja = configuracao("shopify")
    camiseta, bone, _fora = _produtos("Camiseta", "Bone", "Meia")

    resposta = admin_logado.post(LISTA, {
        "action": "sincronizar_com_integracao", "index": 0, "integracao": loja.pk,
        "_selected_action": [camiseta.pk, bone.pk]})

    execucao = _execucao()
    assert resposta.status_code == 302 and str(execucao.pk) in resposta["Location"]
    assert execucao.configuracao == loja
    assert execucao.parametros["recursos"] == ["produtos", "estoque"]
    assert sorted(execucao.parametros["produtos"]) == sorted([camiseta.pk, bone.pk])


def test_botao_do_produto_sincroniza_so_ele(admin_logado, falsos):
    loja = configuracao("shopify")
    camiseta, _bone = _produtos("Camiseta", "Bone")

    resposta = admin_logado.post(reverse("admin:loja_produto_sincronizar", args=[camiseta.pk]),
                                 {"integracao": loja.pk})

    assert resposta.status_code == 302
    assert _execucao().parametros["produtos"] == [camiseta.pk]


def test_sem_integracao_escolhida_nao_cria_tarefa(admin_logado, falsos):
    configuracao("shopify")
    camiseta, = _produtos("Camiseta")

    admin_logado.post(LISTA, {"action": "sincronizar_com_integracao", "index": 0,
                              "_selected_action": [camiseta.pk]})
    admin_logado.post(reverse("admin:loja_produto_sincronizar", args=[camiseta.pk]),
                      {"integracao": "x"})

    assert not ExecucaoIntegracao.objects.exists()


def test_estoque_desligado_vai_so_o_produto(admin_logado, falsos):
    loja = configuracao("shopify", recursos=("produtos",))
    camiseta, = _produtos("Camiseta")

    admin_logado.post(reverse("admin:loja_produto_sincronizar", args=[camiseta.pk]),
                      {"integracao": loja.pk})

    assert _execucao().parametros["recursos"] == ["produtos"]


def test_tarefa_envia_dados_e_estoque_so_dos_produtos_escolhidos(falsos):
    loja = ligar(configuracao("falso"), "estoque", "update")
    camiseta, _fora = _produtos("Camiseta", "Meia")
    execucao = ExecucaoIntegracao.objects.create(
        configuracao=loja, tipo=ExecucaoIntegracao.Tipo.EXPORTAR,
        parametros={"direcao": "exportar", "recursos": ["produtos", "estoque"],
                    "produtos": [camiseta.pk]})

    exportar_dados.run(str(execucao.pk))

    # Estoque de variante sem vinculo e "ignorado" pela base (a variante nao esta la).
    assert falsos == [("falso", "criar", camiseta.pk)]
    execucao.refresh_from_db()
    assert execucao.total == 2  # 1 produto + o estoque da 1 variante dele


def test_dialog_aparece_na_lista_e_no_produto(admin_logado, falsos):
    configuracao("shopify")
    camiseta, = _produtos("Camiseta")

    lista = admin_logado.get(LISTA).content.decode()
    produto = admin_logado.get(reverse("admin:loja_produto_change", args=[camiseta.pk]))

    assert 'id="modal-sincronizar-produtos"' in lista
    assert "sincronizar-produtos.js" in lista
    html = produto.content.decode()
    assert 'data-abrir-modal-etapas="modal-sincronizar-produtos"' in html
    assert reverse("admin:loja_produto_sincronizar", args=[camiseta.pk]) in html
