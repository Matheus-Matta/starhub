"""Listas do admin mostram o codigo do marketplace de origem, nunca o uuid."""

import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.models import ExternalReference, Origin
from apps.loja.admin.codigo_externo import formatar_codigo
from apps.loja.models import Categoria, Cliente, Cupom, Pedido, Produto

ROTA = {
    "produtos": ("produto", Produto), "categorias": ("categoria", Categoria),
    "clientes": ("cliente", Cliente), "cupons": ("cupom", Cupom),
}


def _celula(html, objeto):
    linha = re.search(rf'<tr[^>]*>(?:(?!</tr>).)*?/{objeto.pk}/change/.*?</tr>', html, re.S)
    assert linha, "linha do registro nao encontrada"
    celula = re.search(r'field-codigo_externo[^>]*>(.*?)</td>', linha.group(0), re.S).group(1)
    return re.sub(r'<[^>]+>', '', celula)


def _criar(modelo, sufixo, origem):
    if modelo is Cupom:
        return modelo.objects.create(name=sufixo, origin=origem)
    if modelo is Cliente:
        return modelo.objects.create(nome=sufixo, email=f"{sufixo}@x.test", origin=origem)
    return modelo.objects.create(nome=sufixo, slug=sufixo, origin=origem)


def _vincular(entidade, objeto, externo, plataforma=Origin.SHOPIFY):
    ExternalReference.objects.create(
        platform=plataforma, entity_type=entidade, object_id=str(objeto.pk),
        external_id=externo)


def test_gid_do_shopify_mostra_so_o_numero_final():
    assert formatar_codigo("gid://shopify/Product/123") == "123"
    assert formatar_codigo("ABC-9") == "ABC-9"
    assert formatar_codigo(None) == "-"
    assert formatar_codigo("") == "-"


@pytest.mark.django_db
@pytest.mark.parametrize("entidade", list(ROTA))
def test_lista_mostra_codigo_do_vinculo_da_origem_e_traco_sem_vinculo(admin_logado, entidade):
    """Sem a coluna o operador via so o uuid/ID interno e nao achava o item na loja."""
    rota, modelo = ROTA[entidade]
    shopify = _criar(modelo, "a", Origin.SHOPIFY)
    hub = _criar(modelo, "b", Origin.STARHUB)
    _vincular(entidade, shopify, "gid://shopify/Thing/555")
    # Vinculo de outro marketplace nao vale: so o da origem do registro.
    _vincular(entidade, shopify, "WOO-1", Origin.WOOCOMMERCE)

    html = admin_logado.get(f"/admin/loja/{rota}/").content.decode()

    assert _celula(html, shopify).strip() == "555"
    assert _celula(html, hub).strip() == "-"


@pytest.mark.django_db
def test_pedido_mostra_numero_externo_e_busca_por_ele(admin_logado):
    pedido = Pedido.objects.create(external_number="#1001", origin=Origin.SHOPIFY)
    Pedido.objects.create(external_number="")

    html = admin_logado.get("/admin/loja/pedido/?q=1001").content.decode()

    assert _celula(html, pedido).strip() == "#1001"
    assert html.count("field-codigo_externo") == 1


@pytest.mark.django_db
def test_consultas_da_lista_nao_crescem_com_as_linhas(admin_logado):
    """Um vinculo por linha viraria N+1: 1 e 20 linhas precisam do mesmo numero."""
    def consultas():
        with CaptureQueriesContext(connection) as ctx:
            admin_logado.get("/admin/loja/categoria/")
        return len(ctx)

    c = Categoria.objects.create(nome="C0", slug="c0", origin=Origin.SHOPIFY)
    _vincular("categorias", c, "gid://shopify/Collection/1")
    com_uma = consultas()
    for n in range(1, 20):
        c = Categoria.objects.create(nome=f"C{n}", slug=f"c{n}", origin=Origin.SHOPIFY)
        _vincular("categorias", c, f"gid://shopify/Collection/{n + 1}")

    assert consultas() == com_uma
