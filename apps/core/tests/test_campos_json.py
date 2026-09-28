import html as html_lib
import json

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core import json_normalizar
from apps.loja.admin.campos import FRETE
from apps.loja.models import Categoria, Produto

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def admin_logado(admin_logado, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return admin_logado


def test_tags_sem_repetir_e_mantendo_id_de_quem_ja_existia():
    """Se o id se perder, o ERP que casa tag por id duplica a tag no Woo."""
    saida = json_normalizar.tags(
        [{"id": 7, "name": "Verao", "slug": "verao"}, "verao", " Nova ", ""]
    )
    assert saida == [{"id": 7, "name": "Verao", "slug": "verao"}, {"name": "Nova"}]


def test_metadados_descartam_linha_sem_chave_e_dao_id_as_novas():
    saida = json_normalizar.chave_valor(
        [
            {"id": 3, "key": "ncm", "value": "6109"},
            {"key": " ", "value": "x"},
            {"key": "cor", "value": {"a": 1}},
        ]
    )
    assert saida == [
        {"id": 3, "key": "ncm", "value": "6109"},
        {"key": "cor", "value": {"a": 1}, "id": 4},
    ]


def test_frete_com_virgula_vira_texto_com_ponto_do_woo():
    """O total do pedido soma estes valores com Decimal: "15,9" direto quebraria."""
    saida = json_normalizar.lista(
        [{"method_title": "Sedex", "total": "15,9"}, {}], FRETE, com_id=True
    )
    assert saida == [{"method_title": "Sedex", "total": "15.90", "method_id": "", "id": 1}]


def test_frete_com_valor_que_nao_e_dinheiro_e_recusado():
    with pytest.raises(ValidationError):
        json_normalizar.lista([{"total": "abc"}], FRETE)


def test_endereco_mantem_campos_extras_do_erp():
    campos = [{"campo": "city", "rotulo": "Cidade"}]
    saida = json_normalizar.objeto({"city": " Recife ", "cpf": "123", "vazio": ""}, campos)
    assert saida == {"city": "Recife", "cpf": "123"}


def test_forms_mostram_os_widgets_por_tipo(admin_logado):
    html = admin_logado.get("/admin/loja/produto/add/").content.decode()
    for tipo in ("lista", "chave-valor"):
        assert f'data-json-widget="{tipo}"' in html
    # Dimensoes ("objeto") e a galeria ("imagens") moram no form da variante.
    html = admin_logado.get("/admin/loja/varianteproduto/add/").content.decode()
    for tipo in ("objeto", "imagens"):
        assert f'data-json-widget="{tipo}"' in html
    html = admin_logado.get("/admin/loja/categoria/add/").content.decode()
    assert 'data-json-widget="imagens"' in html
    assert 'enctype="multipart/form-data"' in html


def _dados_categoria(conta, **extra):
    # Superusuario escolhe a conta ao criar (apps/core/admin_conta.py).
    return {"account": conta.pk, "origin": "starhub", "nome": "Canecas", "slug": "canecas",
            "exibicao": "default",
            "ordem": "0", "imagem": "null", "descricao": "", "_save": "Salvar", **extra}


def test_upload_de_imagem_pelo_admin_grava_no_media(admin_logado, tmp_path, conta):
    arquivo = SimpleUploadedFile("foto caneca.png", PNG, content_type="image/png")
    resposta = admin_logado.post(
        "/admin/loja/categoria/add/", _dados_categoria(conta, imagem__arquivos=[arquivo])
    )
    assert resposta.status_code == 302, resposta.content.decode()[:2000]
    imagem = Categoria.objects.get().imagem
    assert imagem["src"].startswith("/media/categorias/") and imagem["name"] == "foto caneca"
    assert (tmp_path / imagem["src"].removeprefix("/media/")).exists()


def test_arquivo_que_nao_e_imagem_e_recusado_mesmo_com_extensao_png(admin_logado, tmp_path,
                                                                    conta):
    falso = SimpleUploadedFile("virus.png", b"MZ\x90\x00 nao sou imagem", content_type="image/png")
    resposta = admin_logado.post(
        "/admin/loja/categoria/add/", _dados_categoria(conta, imagem__arquivos=[falso])
    )
    assert resposta.status_code == 200
    assert "nao e uma imagem" in resposta.content.decode()
    assert not Categoria.objects.exists()
    assert not any(tmp_path.rglob("*.png"))


def test_json_do_admin_e_valido_para_o_widget(admin_logado):
    produto = Produto.objects.create(nome="A", metadados=[{"id": 1, "key": "ncm", "value": "x"}])
    html = admin_logado.get(f"/admin/loja/produto/{produto.pk}/change/").content.decode()
    trecho = html.split('name="metadados"')[1].split(">", 1)[1].split("</textarea>")[0]
    assert json.loads(html_lib.unescape(trecho).strip()) == [{"id": 1, "key": "ncm", "value": "x"}]


def test_rotulo_igual_ao_titulo_so_some_quando_o_campo_esta_sozinho(admin_logado):
    """ "Atributos" (unico campo da secao Atributos) nao repete o rotulo; ja
    "Descricao" divide a secao com "Descricao curta" e precisa do rotulo."""
    html = admin_logado.get("/admin/loja/produto/add/").content.decode()
    assert '<span class="visually-hidden"><label for="id_atributos">' in html
    assert '<span class="visually-hidden"><label for="id_descricao"' not in html
