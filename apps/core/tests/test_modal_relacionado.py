"""Botoes "+"/lapis/olho dos campos de relacao abrem num modal (iframe), nao numa
janela nova. O JS esta em static/starhub/js/modal-relacionado.js; aqui fica o
contrato do servidor que ele precisa."""

import pytest

from apps.loja.models import Tag

pytestmark = pytest.mark.django_db


def test_admin_pode_ser_mostrado_em_iframe_so_pelo_proprio_site(admin_logado):
    """Com o DENY padrao do Django o modal abria vazio (o navegador bloqueia o iframe)."""
    resposta = admin_logado.get("/admin/loja/cliente/add/?_popup=1")
    assert resposta["X-Frame-Options"] == "SAMEORIGIN"


def test_paginas_do_admin_carregam_o_script_do_modal(admin_logado):
    html = admin_logado.get("/admin/loja/pedido/add/").content.decode()
    assert "starhub/js/modal-relacionado.js" in html
    assert 'id="add_id_cliente"' in html  # o "+" que o script intercepta


def test_cancelar_dentro_do_modal_fecha_em_vez_de_ir_para_a_lista(admin_logado):
    popup = admin_logado.get("/admin/loja/cliente/add/?_popup=1").content.decode()
    assert "data-fechar-modal" in popup and 'name="_popup"' in popup
    normal = admin_logado.get("/admin/loja/cliente/add/").content.decode()
    assert "data-fechar-modal" not in normal


def test_resposta_do_popup_avisa_o_parent_quando_nao_ha_opener(admin_logado, conta):
    """A resposta do Django usa window.opener, que nao existe dentro do iframe."""
    resposta = admin_logado.post("/admin/loja/tag/add/?_popup=1", {
        "account": conta.pk, "origin": "starhub", "nome": "Promocao", "slug": "promocao",
        "_popup": "1",
    })
    html = resposta.content.decode()
    assert "starhub/js/popup-resposta.js" in html
    assert "admin/js/popup_response.js" not in html
    assert f"&quot;value&quot;: &quot;{Tag.objects.get().pk}&quot;" in html


def test_marca_de_dentro_do_modal_carrega_no_head_antes_do_tema(admin_logado):
    """No <head>: senao o cabecalho e a barra de salvar da pagina piscam dentro do modal
    antes de o CSS esconder (quem mostra titulo e botoes e o proprio modal)."""
    html = admin_logado.get("/admin/loja/cliente/add/?_popup=1").content.decode()
    cabeca = html.split("</head>", 1)[0]
    assert "starhub/js/em-modal.js" in cabeca
    assert cabeca.index("em-modal.js") < cabeca.index("starhub/css/modal.css")


def test_lista_de_variantes_edita_cada_uma_no_modal(admin_logado):
    """Cada linha abre o form preenchido; produto simples com variante nao mostra o "+"."""
    from apps.loja.services.variantes import criar_produto

    produto = criar_produto("Camiseta", sku="CAM-1")
    variante = produto.variante_padrao
    edicao = admin_logado.get(f"/admin/loja/produto/{produto.pk}/change/").content.decode()
    assert f"/admin/loja/varianteproduto/{variante.pk}/change/?_popup=1" in edicao
    assert "CAM-1" in edicao
    assert 'data-modal-chave="variantes"' not in edicao  # simples: uma variante so


def test_produto_variavel_mostra_o_mais_para_adicionar_variante(admin_logado):
    from apps.loja.models import Produto

    produto = Produto.objects.create(nome="Camiseta", tipo=Produto.Tipo.VARIAVEL)
    edicao = admin_logado.get(f"/admin/loja/produto/{produto.pk}/change/").content.decode()
    assert f"/admin/loja/varianteproduto/add/?produto={produto.pk}" in edicao


def test_variante_do_modal_escolhe_tipo_e_valor_e_ganha_titulo_automatico(admin_logado, conta):
    """Cor + Tamanho escolhidos na variante; titulo em branco vira "Branco / 42"."""
    from apps.loja.models import Produto, TipoVariante, ValorVariante, VarianteProduto

    produto = Produto.objects.create(nome="Tenis", tipo=Produto.Tipo.VARIAVEL)
    cor = TipoVariante.objects.create(nome="Cor", posicao=0)
    tamanho = TipoVariante.objects.create(nome="Tamanho", posicao=1)
    branco = ValorVariante.objects.create(tipo=cor, valor="Branco")
    n42 = ValorVariante.objects.create(tipo=tamanho, valor="42")
    form = admin_logado.get(f"/admin/loja/varianteproduto/add/?produto={produto.pk}").content
    assert b'data-depende-de="tipo"' in form and f'data-pai="{cor.pk}"'.encode() in form
    dados = {"account": conta.pk, "origin": "starhub", "produto": produto.pk, "titulo": "",
             "posicao": "0", "weight_unit": "kg", "inventory_policy": "deny",
             "stock_status": "instock", "tax_status": "taxable", "inventory_quantity": "0",
             "imagens": "[]", "dimensions": "{}", "metadados": "[]",
             "opcoes-TOTAL_FORMS": "2", "opcoes-INITIAL_FORMS": "0",
             "opcoes-0-tipo": cor.pk, "opcoes-0-valor": branco.pk,
             "opcoes-1-tipo": tamanho.pk, "opcoes-1-valor": n42.pk}
    resposta = admin_logado.post("/admin/loja/varianteproduto/add/", dados)
    assert resposta.status_code == 302, resposta.context["adminform"].form.errors
    assert VarianteProduto.objects.get(produto=produto).titulo == "Branco / 42"
    # Dois valores do mesmo tipo na mesma variante: recusado.
    dados.update({"opcoes-1-tipo": cor.pk, "opcoes-1-valor": branco.pk, "sku": "OUTRA"})
    assert admin_logado.post("/admin/loja/varianteproduto/add/", dados).status_code == 200


def test_pagina_do_produto_tem_as_tres_formas(admin_logado):
    """Simples: secoes da variante (Preco, Estoque...). Variavel: lista. Bundle: componentes."""
    html = admin_logado.get("/admin/loja/produto/add/").content.decode()
    assert 'id="variantes-group"' in html and 'class="module aligned secao-estoque' in html
    assert 'name="variantes-0-price"' in html  # preco direto na pagina, sem modal
    assert "secao-variantes" in html and 'id="componentes-group"' in html
    assert html.index("variantes-0-price") < html.index('name="descricao"')  # Descricao no fim


def test_na_criacao_o_clique_salva_o_produto_e_volta_com_o_modal(admin_logado, conta):
    """Sem produto salvo a variante nao tem a quem apontar: salva antes e abre depois."""
    from apps.loja.models import Produto

    criacao = admin_logado.get("/admin/loja/produto/add/").content.decode()
    assert "data-modal-salvar-antes" in criacao  # o JS sabe que precisa salvar antes
    dados = {"account": conta.pk, "origin": "starhub", "nome": "Camiseta", "slug": "camiseta",
             "tipo": "simple", "status": "publish", "visibilidade": "visible",
             "atributos": "[]", "metadados": "[]", "ordem_menu": "0", "id_pai": "0",
             "_continue": "1", "_abrir_modal": "variantes"}
    for prefixo in ("variantes", "componentes"):
        dados.update({f"{prefixo}-TOTAL_FORMS": "0", f"{prefixo}-INITIAL_FORMS": "0"})
    resposta = admin_logado.post("/admin/loja/produto/add/", dados)
    produto = Produto.objects.get()
    assert resposta.status_code == 302
    assert resposta["Location"].startswith(f"/admin/loja/produto/{produto.pk}/change/")
    assert "abrir_modal=variantes" in resposta["Location"]
    # Produto simples nao ganha variante sozinho: o usuario cadastra a dele no modal.
    assert not produto.variantes.exists()


def test_parametro_do_modal_so_aceita_nome_de_formset(admin_logado, conta):
    """O valor volta na URL: texto livre (ex.: script) nao pode passar."""
    dados = {"account": conta.pk, "origin": "starhub", "nome": "X", "slug": "x",
             "tipo": "simple", "status": "publish", "visibilidade": "visible",
             "atributos": "[]", "metadados": "[]", "ordem_menu": "0", "id_pai": "0",
             "_continue": "1", "_abrir_modal": "<script>alert(1)</script>"}
    for prefixo in ("variantes", "componentes"):
        dados.update({f"{prefixo}-TOTAL_FORMS": "0", f"{prefixo}-INITIAL_FORMS": "0"})
    resposta = admin_logado.post("/admin/loja/produto/add/", dados)
    assert "abrir_modal" not in resposta["Location"]
