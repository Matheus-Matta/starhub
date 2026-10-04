import re
from decimal import Decimal
from pathlib import Path

import pytest

from apps.core.tasks import ping
from apps.loja.models import Categoria, Cliente, ItemPedido, Pedido
from apps.loja.services.variantes import criar_produto


@pytest.fixture
def dados_loja():
    Categoria.objects.create(nome="Camisetas", slug="camisetas")
    produto = criar_produto(
        "Camisa azul", sku="CAM-1", price=Decimal("59.90"), inventory_quantity=1
    )
    cliente = Cliente.objects.create(email="ana@cliente.test", nome="Ana")
    pedido = Pedido.objects.create(cliente=cliente, status="processing", total=Decimal("59.90"))
    ItemPedido.objects.create(pedido=pedido, variante=produto.variante_padrao,
                              subtotal=Decimal("59.90"), total=Decimal("59.90"))
    return produto, pedido


def test_login_usa_o_layout_do_tema(client):
    resposta = client.get("/admin/login/")
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert 'class="auth"' in html and 'class="auth-showcase"' in html
    assert 'name="username"' in html and 'name="next"' in html
    for logo in ("woocommerce.svg", "shopify.svg", "shopee.svg"):
        assert f"starhub/img/marcas/{logo}" in html
    assert "auth-security" in html and "auth-network" in html


@pytest.mark.django_db
def test_painel_mostra_indicadores_pedidos_e_estoque_baixo(admin_logado, dados_loja):
    html = admin_logado.get("/admin/").content.decode()
    assert "Receita do mes" in html
    assert "R$ 59,90" in html
    assert "Camisa azul" in html  # estoque 1 -> aparece em "Estoque baixo"
    assert 'class="sidebar"' in html


@pytest.mark.django_db
@pytest.mark.parametrize("url", [
    "/admin/loja/produto/", "/admin/loja/produto/add/", "/admin/loja/pedido/",
    "/admin/loja/pedido/add/", "/admin/loja/cliente/", "/admin/loja/cliente/add/",
    "/admin/loja/categoria/", "/admin/loja/tag/", "/admin/loja/cupom/add/",
    "/admin/loja/tipovariante/add/", "/admin/loja/varianteproduto/",
    "/admin/woo_api/chaveapi/", "/admin/woo_api/chaveapi/add/", "/admin/perfil/",
    "/admin/core/user/", "/admin/core/user/add/", "/admin/core/account/",
    "/admin/core/accessprofile/", "/admin/core/address/",
    "/admin/integracoes/configuracaointegracao/shopify/",
    "/admin/password_change/", "/admin/loja/",
])
def test_telas_do_admin_abrem_com_o_tema(admin_logado, dados_loja, url):
    resposta = admin_logado.get(url)
    assert resposta.status_code == 200
    assert "starhub/css/tokens.css" in resposta.content.decode()


@pytest.mark.django_db
def test_trilha_do_change_list_aparece_no_header(admin_logado, dados_loja):
    """Blocks dentro de include nao sao sobrescritos: se a trilha voltar para um
    include, o change_list passa a mostrar so "Painel" no header."""
    html = admin_logado.get("/admin/loja/produto/").content.decode()
    header = html.split('<header id="header"')[1].split("</header>")[0]
    assert "Produtos" in header


@pytest.mark.django_db
def test_listagem_usa_card_com_toolbar_tabela_e_paginacao(admin_logado, dados_loja):
    """A listagem nao pode voltar a ser blocos soltos do admin entre o titulo e a tabela."""
    html = admin_logado.get("/admin/loja/produto/").content.decode()
    assert 'class="list-card-header"' in html
    assert 'class="list-card-table"' in html
    assert 'class="list-card-footer"' in html
    assert 'class="list-search"' in html
    assert 'data-acao="abrir-filtros"' in html


def test_listagem_estica_todos_os_blocos_ate_a_largura_do_card():
    """O align-items do Django nao pode encolher toolbar, tabela e rodape."""
    raiz = Path(__file__).resolve().parents[3]
    css = (raiz / "static/starhub/css/admin-lista.css").read_text(encoding="utf-8")
    regra = "body.change-list #changelist.list-card"
    assert f"{regra} {{\n    align-items: stretch;\n    width: 100%;" in css


@pytest.mark.django_db
def test_listagem_sem_dados_mostra_estado_vazio_dentro_da_tabela(admin_logado):
    """Uma lista vazia precisa explicar o espaco em branco dentro do card."""
    html = admin_logado.get("/admin/loja/produto/").content.decode()
    area_tabela = html.split('class="list-card-table"', 1)[1].split("</div>", 1)[0]
    assert 'class="empty-state"' in area_tabela
    assert "Nenhum registro encontrado." in area_tabela


@pytest.mark.django_db
@pytest.mark.parametrize("sufixo", ["add/", "1/change/"])
def test_criacao_e_edicao_usam_workspace_de_formulario(admin_logado, dados_loja, sufixo):
    """Criar e editar compartilham a mesma arquitetura visual e as mesmas acoes."""
    html = admin_logado.get(f"/admin/loja/produto/{sufixo}").content.decode()
    assert 'class="form-workspace form-workspace-flat"' in html
    assert 'class="form-workspace-header"' in html
    assert 'class="form-card-grid form-card-grid-single"' in html
    assert 'class="submit-actions"' in html
    assert 'name="_save"' in html


@pytest.mark.django_db
def test_workspace_do_formulario_nao_cria_card_externo(admin_logado, dados_loja):
    """Os cards de secoes ficam direto na pagina, sem uma segunda moldura ao redor."""
    html = admin_logado.get("/admin/loja/produto/add/").content.decode()
    assert 'class="form-workspace form-workspace-flat"' in html


@pytest.mark.django_db
def test_todas_as_secoes_recolhiveis_iniciam_abertas(admin_logado, dados_loja):
    """Secoes como Descricao e Avancado devem mostrar os campos ao abrir a tela."""
    html = admin_logado.get("/admin/loja/produto/add/").content.decode()
    assert "Avancado" in html
    secoes = re.split(r'<fieldset class="module aligned collapse[^"]*"', html)[1:]
    assert secoes
    assert all("<details open>" in secao.split("</fieldset>", 1)[0] for secao in secoes)


@pytest.mark.django_db
def test_secoes_do_formulario_ficam_em_uma_coluna(admin_logado, dados_loja):
    """Cada secao ocupa uma linha; apenas os campos internos podem formar colunas."""
    html = admin_logado.get("/admin/loja/produto/add/").content.decode()
    assert 'class="form-card-grid form-card-grid-single"' in html


@pytest.mark.django_db
def test_telas_de_edicao_de_pedido_e_cliente_abrem(admin_logado, dados_loja):
    _, pedido = dados_loja
    for url in (f"/admin/loja/pedido/{pedido.pk}/change/",
                f"/admin/loja/cliente/{pedido.cliente_id}/change/"):
        assert admin_logado.get(url).status_code == 200, url


def _inline_vazio(prefixo):
    return {f"{prefixo}-TOTAL_FORMS": "0", f"{prefixo}-INITIAL_FORMS": "0",
            f"{prefixo}-MIN_NUM_FORMS": "0", f"{prefixo}-MAX_NUM_FORMS": "1000"}


@pytest.mark.django_db
def test_edicao_de_pedido_pelo_admin_recalcula_o_total(admin_logado, dados_loja):
    produto, pedido = dados_loja
    item = pedido.itens.get()
    dados = {
        "number": pedido.number, "status": "processing", "moeda": "BRL",
        "financial_status": "paid", "fulfillment_status": "unfulfilled",
        "cliente": pedido.cliente_id, "cobranca_city": "Recife", "cobranca_postcode": "50030-230",
        "linhas_frete": "[]", "linhas_taxa": "[]", "linhas_cupom": "[]", "metadados": "[]",
        "itens-TOTAL_FORMS": "1", "itens-INITIAL_FORMS": "1",
        "itens-MIN_NUM_FORMS": "0", "itens-MAX_NUM_FORMS": "1000",
        "itens-0-id": item.pk, "itens-0-pedido": pedido.pk, "itens-0-produto": produto.pk,
        "itens-0-nome": "Camisa azul", "itens-0-sku": "CAM-1", "itens-0-quantidade": "3",
        "itens-0-subtotal": "", "itens-0-total": "",
        **_inline_vazio("pagamentos"), **_inline_vazio("entregas"),
    }
    resposta = admin_logado.post(f"/admin/loja/pedido/{pedido.pk}/change/", dados)
    assert resposta.status_code == 302, resposta.content.decode()[:3000]
    pedido.refresh_from_db()
    assert pedido.total == Decimal("179.70")
    cobranca = pedido.endereco_cobranca
    assert (cobranca.city, cobranca.postal_code) == ("Recife", "50030230")


def test_celery_em_dev_executa_a_tarefa_na_hora():
    assert ping.delay().get(timeout=1) == "pong"
