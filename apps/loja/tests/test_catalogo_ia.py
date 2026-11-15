import base64
from decimal import Decimal

import pytest

from apps.core.tenant.context import tenant_context
from apps.loja.models import ItemBundle, Produto, VarianteProduto
from apps.loja.services.variantes import criar_produto
from apps.woo_api.models import ChaveApi

pytestmark = pytest.mark.django_db

URL = "/catalogo/ia/"


def _autorizar(cliente, *, conta=None, scopes=None):
    registro = ChaveApi(
        descricao="Leitura pela IA",
        permissao=ChaveApi.Permissao.LEITURA,
        scopes=["catalogo_ia"] if scopes is None else scopes,
        **({"account": conta} if conta else {}),
    )
    chave, segredo = registro.gerar()
    registro.save()
    credencial = base64.b64encode(f"{chave}:{segredo}".encode()).decode()
    cliente.defaults["HTTP_AUTHORIZATION"] = f"Basic {credencial}"
    return registro


def test_catalogo_recusa_acesso_sem_chave_e_chave_sem_escopo(client):
    """A URL conhecida nao pode transformar o catalogo inteiro em informacao publica."""
    assert client.get(URL).status_code == 401

    _autorizar(client, scopes=[])
    assert client.get(URL).status_code == 403


def test_catalogo_nao_aceita_segredo_na_url(client):
    """Credencial na query vazaria em historico, proxy e logs de acesso."""
    registro = ChaveApi(
        descricao="IA", permissao=ChaveApi.Permissao.LEITURA, scopes=["catalogo_ia"]
    )
    chave, segredo = registro.gerar()
    registro.save()

    resposta = client.get(f"{URL}?consumer_key={chave}&consumer_secret={segredo}")

    assert resposta.status_code == 401


def test_chave_do_catalogo_nao_abre_as_demais_rotas_da_api(client):
    """Uma chave exposta a IA nao pode ler pedidos, clientes nem outros dados do ERP."""
    criar_produto("Produto", sku="PRO-1", price=Decimal("10.00"))
    _autorizar(client)

    resposta = client.get("/wp-json/wc/v1/products")

    assert resposta.status_code == 401


def test_cada_variacao_vira_linha_com_nome_sku_e_preco(client):
    """Paginar produtos esconderia variacoes da IA e misturaria seus precos e SKUs."""
    produto = Produto.objects.create(
        nome="Camiseta <script>alert(1)</script>",
        tipo=Produto.Tipo.VARIAVEL,
        descricao="<p>Algodao & conforto</p>",
    )
    for titulo, sku, preco in (
        ("Azul / P", "CAM-AZ-P", "79.90"),
        ("Azul / M", "CAM-AZ-M", "89.90"),
        ("Preta / P", "CAM-PR-P", "84.90"),
        ("Preta / M", "CAM-PR-M", "94.90"),
    ):
        VarianteProduto.objects.create(
            produto=produto, titulo=titulo, sku=sku, price=Decimal(preco)
        )
    _autorizar(client)

    resposta = client.get(URL)
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert resposta["Content-Type"].startswith("text/html")
    assert resposta["Cache-Control"] == "private, no-store, max-age=0"
    assert resposta["X-Robots-Tag"].startswith("noindex")
    assert resposta["Content-Security-Policy"].startswith("default-src 'none'")
    assert html.count("<tr data-item") == 4
    assert "Camiseta &lt;script&gt;alert(1)&lt;/script&gt; - Azul / P" in html
    assert "CAM-AZ-M" in html
    assert "94.90" in html
    assert "<script>alert(1)</script>" not in html


def test_kit_vira_uma_linha_com_composicao_e_estoque_calculado(client):
    """Um kit sem composicao faria a IA oferecer um item diferente do que sera entregue."""
    mouse = criar_produto(
        "Mouse", sku="MOU-1", price=Decimal("50.00"), inventory_quantity=10
    )
    pilha = criar_produto(
        "Pilha", sku="PIL-1", price=Decimal("5.00"), inventory_quantity=6
    )
    kit = Produto.objects.create(nome="Kit Gamer", tipo=Produto.Tipo.BUNDLE)
    VarianteProduto.objects.create(produto=kit, sku="KIT-1", price=Decimal("99.90"))
    ItemBundle.objects.create(
        bundle_product=kit, component_variant=mouse.variante_padrao, quantity=1
    )
    ItemBundle.objects.create(
        bundle_product=kit, component_variant=pilha.variante_padrao, quantity=2
    )
    _autorizar(client)

    resposta = client.get(URL)
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert "Kit Gamer" in html
    assert "1 x Mouse (MOU-1)" in html
    assert "2 x Pilha (PIL-1)" in html
    assert ">3</td>" in html


def test_catalogo_expoe_somente_itens_publicaveis_da_conta_da_chave(
    client, conta, outra_conta
):
    """Uma chave nunca pode atravessar tenant nem revelar rascunho ou produto oculto."""
    criar_produto("Publicado", sku="PUB-1", price=Decimal("10.00"))
    criar_produto("Rascunho", sku="RAS-1", price=Decimal("10.00"))
    rascunho = Produto.objects.get(nome="Rascunho")
    rascunho.status = Produto.Status.RASCUNHO
    rascunho.save()
    oculto = criar_produto("Oculto", sku="OCU-1", price=Decimal("10.00"))
    oculto.visibilidade = Produto.Visibilidade.OCULTO
    oculto.save()
    inativo = criar_produto("Inativo", sku="INA-1", price=Decimal("10.00"))
    inativo.active = False
    inativo.save()
    with tenant_context(outra_conta):
        criar_produto("Outra conta", sku="OUT-1", price=Decimal("10.00"))
    _autorizar(client, conta=conta)

    html = client.get(URL).content.decode()

    assert "Publicado" in html
    assert "Rascunho" not in html
    assert "Oculto" not in html
    assert "Inativo" not in html
    assert "Outra conta" not in html


def test_paginacao_tem_mil_por_padrao_e_aceita_quantidade_na_url(client):
    """O consumidor precisa percorrer todas as linhas sem repetir nem perder uma."""
    produto = Produto.objects.create(nome="Produto variavel", tipo=Produto.Tipo.VARIAVEL)
    VarianteProduto.objects.bulk_create([
        VarianteProduto(
            produto=produto,
            titulo=f"Variacao {numero:03d}",
            sku=f"SKU-{numero:03d}",
            price=Decimal("10.00"),
            account=produto.account,
        )
        for numero in range(1001)
    ])
    _autorizar(client)

    primeira = client.get(f"{URL}?page=1")
    segunda = client.get(f"{URL}?page=2")
    personalizada = client.get(f"{URL}?page=2&per_page=40")

    assert primeira.content.decode().count("<tr data-item") == 1000
    assert segunda.content.decode().count("<tr data-item") == 1
    assert personalizada.content.decode().count("<tr data-item") == 40
    assert 'rel="next" href="?page=2&amp;per_page=1000"' in primeira.content.decode()
    assert 'rel="next" href="?page=3&amp;per_page=40"' in personalizada.content.decode()
    assert primeira["X-Catalog-Total"] == "1001"
    assert primeira["X-Catalog-Total-Pages"] == "2"
    assert personalizada["X-Catalog-Per-Page"] == "40"


def test_quantidade_por_pagina_precisa_ficar_no_limite_seguro(client):
    """Uma URL forjada nao pode consumir memoria tentando montar uma resposta sem limite."""
    _autorizar(client)

    assert client.get(f"{URL}?per_page=0").status_code == 400
    assert client.get(f"{URL}?per_page=5001").status_code == 400
    assert client.get(f"{URL}?per_page=texto").status_code == 400
