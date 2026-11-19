from decimal import Decimal

import pytest

from apps.core.tenant.context import tenant_context
from apps.loja.models import ItemBundle, Produto, VarianteProduto
from apps.loja.services.variantes import criar_produto

pytestmark = pytest.mark.django_db


def _url(conta, **params):
    query = "&".join(f"{chave}={valor}" for chave, valor in params.items())
    caminho = f"/{conta.pk}/catalogo/public/"
    return f"{caminho}?{query}" if query else caminho


def _publicar(conta):
    conta.catalogo_publico = True
    conta.save(update_fields=["catalogo_publico"])


def test_catalogo_desligado_responde_404_e_ligado_e_publico(client, conta):
    """Conhecer o UUID nao publica nada ate o dono da conta escolher publicar."""
    assert client.get(_url(conta)).status_code == 404

    _publicar(conta)
    resposta = client.get(_url(conta))

    assert resposta.status_code == 200
    assert resposta["Content-Type"].startswith("text/html")
    assert resposta["Cache-Control"] == "no-store, max-age=0"
    assert resposta["X-Robots-Tag"].startswith("noindex")


def test_catalogo_publico_abre_com_sessao_do_admin(admin_logado, conta):
    """O DRF troca o usuario da rota publica por anonimo sem invalidar o tenant ligado."""
    _publicar(conta)

    resposta = admin_logado.get(_url(conta))

    assert resposta.status_code == 200


def test_catalogo_de_conta_inativa_responde_404(client, conta):
    """Desativar a conta precisa retirar imediatamente seu catalogo publico do ar."""
    conta.catalogo_publico = True
    conta.active = False
    conta.save(update_fields=["catalogo_publico", "active"])

    assert client.get(_url(conta)).status_code == 404


def test_cada_variacao_vira_linha_com_conteudo_seguro(client, conta):
    """Cada SKU precisa de linha propria e texto cadastrado nunca pode executar script."""
    produto = Produto.objects.create(
        nome="Camiseta <script>alert(1)</script>", tipo=Produto.Tipo.VARIAVEL
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
    _publicar(conta)

    html = client.get(_url(conta)).content.decode()

    assert html.count("<tr data-item") == 4
    assert "Camiseta &lt;script&gt;alert(1)&lt;/script&gt; - Azul / P" in html
    assert "CAM-AZ-M" in html and "94.90" in html
    assert "<script>alert(1)</script>" not in html


def test_kit_vira_uma_linha_com_composicao_e_estoque(client, conta):
    """A IA precisa saber o que existe dentro do kit e quantos kits podem ser vendidos."""
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
    _publicar(conta)

    html = client.get(_url(conta)).content.decode()

    assert "1 x Mouse (MOU-1)" in html
    assert "2 x Pilha (PIL-1)" in html
    assert ">3</td>" in html


def test_uuid_isola_contas_e_catalogo_mostra_so_publicaveis(client, conta, outra_conta):
    """O UUID da URL define o tenant e rascunho, oculto ou inativo nunca sai."""
    criar_produto("Publicado", sku="PUB-1", price=Decimal("10.00"))
    rascunho = criar_produto("Rascunho", sku="RAS-1", price=Decimal("10.00"))
    rascunho.status = Produto.Status.RASCUNHO
    rascunho.save()
    oculto = criar_produto("Oculto", sku="OCU-1", price=Decimal("10.00"))
    oculto.visibilidade = Produto.Visibilidade.OCULTO
    oculto.save()
    with tenant_context(outra_conta):
        criar_produto("Outra conta", sku="OUT-1", price=Decimal("10.00"))
    _publicar(conta)
    _publicar(outra_conta)

    nosso = client.get(_url(conta)).content.decode()
    deles = client.get(_url(outra_conta)).content.decode()

    assert "Publicado" in nosso
    assert "Rascunho" not in nosso and "Oculto" not in nosso
    assert "Outra conta" not in nosso and "Outra conta" in deles


def test_paginacao_tem_mil_por_padrao_e_aceita_quantidade_na_url(client, conta):
    """A integracao escolhe o lote sem repetir nem perder variantes entre paginas."""
    produto = Produto.objects.create(nome="Produto variavel", tipo=Produto.Tipo.VARIAVEL)
    VarianteProduto.objects.bulk_create([
        VarianteProduto(
            produto=produto, titulo=f"Variacao {n:04d}", sku=f"SKU-{n:04d}",
            price=Decimal("10.00"), account=produto.account,
        )
        for n in range(1001)
    ])
    _publicar(conta)

    primeira = client.get(_url(conta, page=1))
    segunda = client.get(_url(conta, page=2))
    personalizada = client.get(_url(conta, page=2, per_page=40))

    assert primeira.content.decode().count("<tr data-item") == 1000
    assert segunda.content.decode().count("<tr data-item") == 1
    assert personalizada.content.decode().count("<tr data-item") == 40
    assert primeira["X-Catalog-Total"] == "1001"
    assert personalizada["X-Catalog-Per-Page"] == "40"
    assert 'rel="next" href="?page=3&amp;per_page=40"' in personalizada.content.decode()


def test_quantidade_por_pagina_precisa_ficar_no_limite_seguro(client, conta):
    """Uma URL forjada nao pode consumir memoria tentando montar resposta sem limite."""
    _publicar(conta)

    assert client.get(_url(conta, per_page=0)).status_code == 400
    assert client.get(_url(conta, per_page=5001)).status_code == 400
    assert client.get(_url(conta, per_page="texto")).status_code == 400
    assert client.get("/catalogo/ia/").status_code == 404
