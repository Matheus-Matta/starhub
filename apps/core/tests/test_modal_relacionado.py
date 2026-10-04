"""Botoes "+"/lapis/olho dos campos de relacao abrem num modal (iframe), nao numa
janela nova. O JS esta em static/starhub/js/modal-relacionado.js; aqui fica o
contrato do servidor que ele precisa."""

import re

import pytest

from apps.loja.models import Tag

SECAO_CONTA = re.compile(r'class="fieldset-heading">\s*Conta\s*<')

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
    """Cada linha abre o form preenchido. O "+" ja vem na pagina: trocar o tipo para
    Variavel mostra a secao (e o botao) sem precisar salvar."""
    from apps.loja.services.variantes import criar_produto

    produto = criar_produto("Camiseta", sku="CAM-1")
    variante = produto.variante_padrao
    edicao = admin_logado.get(f"/admin/loja/produto/{produto.pk}/change/").content.decode()
    assert f"/admin/loja/varianteproduto/{variante.pk}/change/?_popup=1" in edicao
    assert "CAM-1" in edicao
    assert 'data-modal-chave="variantes"' in edicao


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


def test_mais_com_produto_alterado_salva_e_volta_abrindo_o_modal(admin_logado, conta):
    """Tipo trocado para Variavel e nao salvo: o "+" salva antes (senao a variante nova
    seria recusada pela regra "produto simples tem uma so") e a edicao reabre o modal."""
    from apps.loja.models import Produto
    from apps.loja.services.variantes import criar_produto

    produto = criar_produto("Camiseta", sku="CAM-1")
    dados = {"nome": "Camiseta", "slug": produto.slug, "tipo": "variable", "status": "publish",
             "visibilidade": "visible", "atributos": "[]", "metadados": "[]",
             "ordem_menu": "0", "id_pai": "0", "_continue": "1", "_abrir_modal": "variantes",
             "variantes-TOTAL_FORMS": "1", "variantes-INITIAL_FORMS": "1",
             "variantes-0-id": produto.variante_padrao.pk, "variantes-0-produto": produto.pk,
             "variantes-0-sku": "CAM-1", "variantes-0-imagens": "[]",
             "variantes-0-dimensions": "{}", "variantes-0-weight_unit": "kg",
             "variantes-0-inventory_policy": "deny", "variantes-0-stock_status": "instock",
             "variantes-0-tax_status": "taxable", "variantes-0-inventory_quantity": "0",
             "variantes-0-posicao": "0",
             "componentes-TOTAL_FORMS": "0", "componentes-INITIAL_FORMS": "0"}
    resposta = admin_logado.post(f"/admin/loja/produto/{produto.pk}/change/", dados)
    assert resposta.status_code == 302, resposta.context and resposta.context["errors"]
    assert "abrir_modal=variantes" in resposta["Location"]
    assert Produto.objects.get().tipo == "variable"


def test_modal_aberto_pelo_produto_esconde_conta_e_produto(admin_logado, outra_conta):
    """Variante aberta na pagina do produto: o produto ja esta decidido e a conta vem
    dele (mesmo sendo de outra conta que a do superusuario)."""
    from apps.core.tenant.context import tenant_context
    from apps.loja.models import Produto, VarianteProduto

    with tenant_context(outra_conta):
        produto = Produto.objects.create(nome="Tenis", tipo=Produto.Tipo.VARIAVEL)
    url = f"/admin/loja/varianteproduto/add/?produto={produto.pk}&_popup=1"
    pagina = admin_logado.get(url).content.decode()
    assert 'name="account"' not in pagina and not SECAO_CONTA.search(pagina)
    assert f'type="hidden" name="produto" value="{produto.pk}"' in pagina
    dados = {"produto": produto.pk, "titulo": "Unica", "posicao": "0", "weight_unit": "kg",
             "inventory_policy": "deny", "stock_status": "instock", "tax_status": "taxable",
             "inventory_quantity": "0", "imagens": "[]", "dimensions": "{}", "metadados": "[]",
             "opcoes-TOTAL_FORMS": "0", "opcoes-INITIAL_FORMS": "0", "_popup": "1"}
    resposta = admin_logado.post(url, dados)
    assert resposta.status_code == 200 and b"errornote" not in resposta.content
    variante = VarianteProduto.all_objects.get(produto=produto)
    assert variante.account_id == outra_conta.pk
    # Edicao pelo modal: tambem sem conta e sem o select de produto.
    pagina = admin_logado.get(f"/admin/loja/varianteproduto/{variante.pk}/change/?_popup=1")
    assert not SECAO_CONTA.search(pagina.content.decode())
    # Fora do modal (menu Variantes) continua tudo.
    pagina = admin_logado.get(f"/admin/loja/varianteproduto/{variante.pk}/change/").content.decode()
    assert SECAO_CONTA.search(pagina) and 'name="produto"' in pagina
    assert 'type="hidden" name="produto"' not in pagina
