from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from apps.loja.models import Cliente, Pedido, Produto
from apps.loja.services.variantes import criar_produto


def _pedido_em(dia, **campos):
    pedido = Pedido.objects.create(**campos)
    quando = timezone.make_aware(datetime(2026, 9, dia, 23, 30))
    Pedido.objects.filter(pk=pedido.pk).update(created_at=quando)
    return pedido


def test_busca_do_header_usa_os_search_fields_de_cada_admin(admin_logado):
    criar_produto("Caneca azul", sku="CAN-9", price=Decimal("10"))
    Cliente.objects.create(email="caneca@cliente.test")
    html = admin_logado.get("/admin/busca/?q=caneca").content.decode()
    assert "Caneca azul" in html
    assert "caneca@cliente.test" in html


def test_busca_com_uma_letra_nao_consulta_nada(admin_logado):
    Produto.objects.create(nome="A")
    html = admin_logado.get("/admin/busca/?q=a").content.decode()
    assert "Digite pelo menos 2 letras" in html


def test_filtro_periodo_inclui_o_ultimo_dia_inteiro(admin_logado):
    """Pedido das 23h30 do dia 30 precisa entrar em "ate 30/09". Comparando
    datetime com a data (meia-noite) ele ficaria de fora."""
    dentro = _pedido_em(30)
    _pedido_em(10)
    url = "/admin/loja/pedido/?created_at__date__gte=2026-09-20&created_at__date__lte=2026-09-30"
    resposta = admin_logado.get(url)
    assert resposta.status_code == 200
    assert list(resposta.context["cl"].queryset) == [dentro]


def test_filtro_periodo_com_data_impossivel_e_ignorado(admin_logado):
    _pedido_em(10)
    resposta = admin_logado.get("/admin/loja/pedido/?created_at__date__gte=2026-02-30")
    assert resposta.status_code == 200
    assert resposta.context["cl"].result_count == 1


def test_filtro_periodo_mantem_os_outros_filtros_ao_aplicar(admin_logado):
    _pedido_em(10, status="completed")
    html = admin_logado.get("/admin/loja/pedido/?status__exact=completed").content.decode()
    assert 'name="status__exact" value="completed"' in html


def test_botao_filtros_conta_filtros_e_nao_parametros(admin_logado):
    """O periodo usa dois parametros (de/ate); o contador tem que mostrar 2
    filtros (periodo + status), nao 3."""
    url = ("/admin/loja/pedido/?created_at__date__gte=2026-09-01"
           "&created_at__date__lte=2026-09-30&status__exact=completed")
    html = admin_logado.get(url).content.decode()
    botao = html.split('data-acao="abrir-filtros"')[1].split("</button>")[0]
    assert '<span class="badge badge-primary">2</span>' in botao


def test_filtros_ficam_na_gaveta_com_o_id_que_o_admin_usa(admin_logado):
    html = admin_logado.get("/admin/loja/produto/").content.decode()
    assert 'id="changelist-filter" class="drawer"' in html
    assert 'class="drawer-corpo"' in html
