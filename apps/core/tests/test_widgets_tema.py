import re

from django import forms
from django.template import Context, Template

from apps.core.widgets import DataHoraTema, DataTema, SwitchTema


def test_form_do_produto_usa_os_widgets_do_tema(admin_logado):
    html = admin_logado.get("/admin/loja/varianteproduto/add/").content.decode()
    # Data da promocao (na variante): calendario em modo periodo ligado ao campo final.
    assert 'data-periodo-fim="sale_ends_at"' in html
    assert 'name="sale_starts_at_1"' in html and 'type="time"' in html
    # Booleano vira switch.
    assert 'class="switch"' in html and 'role="switch"' in html
    # Categorias: select multiple comum (o JS monta o multi-select), sem as
    # duas caixas do filter_horizontal e sem o aviso de segurar Ctrl.
    assert 'class="selectfilter' not in html
    assert not re.search(r"\bControl\b", html)  # "Controlar estoque" e rotulo nosso


def test_data_tema_mostra_e_aceita_dd_mm_aaaa():
    class Form(forms.Form):
        dia = forms.DateField(widget=DataTema())

    form = Form(data={"dia": "27/09/2026"})
    assert form.is_valid(), form.errors
    assert "27/09/2026" in str(Form(initial={"dia": form.cleaned_data["dia"]})["dia"])


def test_data_hora_tema_e_compativel_com_split_datetime():
    class Form(forms.Form):
        quando = forms.SplitDateTimeField(widget=DataHoraTema())

    form = Form(data={"quando_0": "27/09/2026", "quando_1": "14:30"})
    assert form.is_valid(), form.errors
    assert (form.cleaned_data["quando"].hour, form.cleaned_data["quando"].minute) == (14, 30)


def test_switch_tema_continua_checkbox():
    html = SwitchTema().render("ativo", True)
    assert 'type="checkbox"' in html and "checked" in html and 'class="switch"' in html


def test_forms_html_poe_booleano_como_switch_com_rotulo_em_cima():
    class Form(forms.Form):
        ativo = forms.BooleanField(required=False)

    html = Template('{% include "components/forms.html" with form=form %}').render(
        Context({"form": Form()})
    )
    assert html.index("<label") < html.index('class="field-switch"')


def test_header_tem_busca_e_nao_tem_mais_rodape(admin_logado):
    html = admin_logado.get("/admin/").content.decode()
    assert 'data-atalho-busca' in html
    assert "app-footer" not in html


def _celula(html, campo):
    """Classe da celula que contem o campo `campo` no change_form."""
    antes = html.split(f'name="{campo}"')[0]
    return antes.rsplit('<div class="celula', 1)[1].split('"', 1)[0]


def test_select_texto_e_tags_ocupam_uma_coluna_e_json_duas(admin_logado):
    """Select e texto sozinhos na linha nao podem esticar nas duas colunas;
    descricao e tabelas JSON ocupam a largura toda."""
    html = admin_logado.get("/admin/loja/produto/add/").content.decode()
    for estreito in ("slug", "categorias", "tags", "tipo", "fornecedor"):
        assert "celula-larga" not in _celula(html, estreito), estreito
    for largo in ("descricao", "atributos", "metadados"):
        assert "celula-larga" in _celula(html, largo), largo


def test_switch_marca_celula_para_centralizar(admin_logado):
    html = admin_logado.get("/admin/loja/produto/add/").content.decode()
    assert "celula-switch" in _celula(html, "destaque")
    assert "celula-switch" not in _celula(html, "visibilidade")
