from decimal import Decimal

from django.template import Context, Template

from apps.core.ui.formatos import moeda
from apps.core.ui.menu import agrupar_apps, montar_menu


def renderizar(texto, **contexto):
    return Template(texto).render(Context(contexto))


def test_componente_entrega_conteudo_e_slot_nomeado_ao_card():
    """O {% componente %} existe para ter "slot"; se o slot nomeado vazar para o
    corpo (ou sumir), o botao de acao do card aparece no lugar errado."""
    html = renderizar(
        '{% componente "card" titulo="Pedidos" %}'
        '{% slot "acoes" %}<a id="acao">Ver</a>{% endslot %}<p id="corpo">oi</p>'
        "{% endcomponente %}"
    )
    cabecalho, corpo = html.split('class="card-body')
    assert 'id="acao"' in cabecalho
    assert 'id="corpo"' in corpo
    assert 'id="acao"' not in corpo


def test_slot_de_componente_aninhado_fica_no_componente_de_dentro():
    """Sem filtrar os slots so do primeiro nivel, o card de fora pegaria a acao
    do card de dentro e ela sairia duplicada."""
    html = renderizar(
        '{% componente "card" titulo="Fora" %}'
        '{% componente "card" titulo="Dentro" %}{% slot "acoes" %}X-ACAO{% endslot %}'
        "{% endcomponente %}{% endcomponente %}"
    )
    assert html.count("X-ACAO") == 1


def test_moeda_formata_no_padrao_brasileiro_sem_depender_do_locale():
    assert moeda(Decimal("1234.5")) == "R$ 1.234,50"
    assert moeda(Decimal("-0.005")) == "-R$ 0,01"
    assert moeda(None) == "R$ 0,00"


def test_menu_acende_so_o_item_mais_especifico():
    """/admin/loja/pedido/ tambem comeca com /admin/loja/ -- se os dois acendessem
    o usuario nao saberia em que tela esta."""
    apps = [{
        "name": "Loja", "app_label": "loja",
        "models": [
            {"name": "Loja geral", "admin_url": "/admin/loja/"},
            {"name": "Pedidos", "admin_url": "/admin/loja/pedido/"},
        ],
    }]
    grupo = montar_menu(apps, "/admin/loja/pedido/3/change/")[0]
    ativos = [item["nome"] for item in grupo["itens"] if item["ativo"]]
    assert ativos == ["Pedidos"]


def test_agrupar_move_chaves_de_api_para_autenticacao():
    """A secao "API WooCommerce" some e "Chaves de API" aparece em Autenticacao."""
    apps = [
        {"app_label": "auth", "name": "Autenticacao", "models": [{"name": "Usuarios"}]},
        {"app_label": "woo_api", "name": "API WooCommerce", "models": [{"name": "Chaves de API"}]},
    ]
    resultado = agrupar_apps(apps, {"woo_api": "auth"})
    assert [app["app_label"] for app in resultado] == ["auth"]
    assert [m["name"] for m in resultado[0]["models"]] == ["Chaves de API", "Usuarios"]
    assert resultado[0]["models"][0]["app_label"] == "woo_api"  # icone continua o da chave


def test_agrupar_nao_some_com_o_item_se_o_destino_nao_aparece():
    """Usuario sem acesso a Autenticacao ainda precisa ver as chaves em algum lugar."""
    apps = [{"app_label": "woo_api", "name": "API WooCommerce", "models": [{"name": "Chaves"}]}]
    assert agrupar_apps(apps, {"woo_api": "auth"}) == apps
