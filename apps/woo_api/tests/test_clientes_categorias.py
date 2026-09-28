from apps.loja.models import Categoria, Cliente

URL = "/wp-json/wc/v1/customers"
URL_CATEGORIAS = "/wp-json/wc/v1/products/categories"


def test_cliente_exige_email(api):
    resposta = api.post(URL, {"first_name": "Ana"}, format="json")
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "rest_missing_callback_param"


def test_email_repetido_mesmo_com_maiusculas_devolve_erro_do_woo(api):
    api.post(URL, {"email": "ana@cliente.test"}, format="json")
    resposta = api.post(URL, {"email": "ANA@Cliente.test"}, format="json")
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "registration-error-email-exists"


def test_filtro_por_email_encontra_o_cliente(api):
    api.post(URL, {"email": "ana@cliente.test", "first_name": "Ana"}, format="json")
    encontrados = api.get(f"{URL}?email=Ana@Cliente.test").json()
    assert [c["first_name"] for c in encontrados] == ["Ana"]


def test_campos_brasileiros_do_endereco_sao_preservados(api):
    """ERPs brasileiros leem cpf/number/neighborhood do billing (plugin Brazilian
    Market). Se o hub descartar o que nao conhece, a nota fiscal sai sem CPF."""
    corpo = api.post(URL, {"email": "a@b.test", "billing": {
        "cpf": "123.456.789-09", "number": "100", "neighborhood": "Centro", "city": "Recife",
    }}, format="json").json()
    assert corpo["billing"]["cpf"] == "123.456.789-09"
    assert corpo["billing"]["neighborhood"] == "Centro"
    assert corpo["billing"]["address_1"] == ""  # campos padrao continuam la
    alterado = api.put(f"{URL}/{corpo['id']}", {"billing": {"city": "Olinda"}}, format="json")
    assert alterado.json()["billing"]["cpf"] == "123.456.789-09"


def test_cliente_nao_vai_para_lixeira_sem_force(api):
    cliente = Cliente.objects.create(email="a@b.test")
    resposta = api.delete(f"{URL}/{cliente.pk}")
    assert resposta.status_code == 501
    assert resposta.json()["code"] == "woocommerce_rest_trash_not_supported"
    assert api.delete(f"{URL}/{cliente.pk}?force=true").status_code == 200


def test_categoria_repetida_devolve_term_exists_com_id(api):
    """ERPs criam a categoria e, se ela ja existe, usam o resource_id do erro."""
    primeira = api.post(URL_CATEGORIAS, {"name": "Canecas"}, format="json").json()
    resposta = api.post(URL_CATEGORIAS, {"name": "canecas"}, format="json")
    assert resposta.status_code == 400
    assert resposta.json()["code"] == "term_exists"
    assert resposta.json()["data"]["resource_id"] == primeira["id"]


def test_mesmo_nome_em_outro_pai_ganha_slug_com_sufixo(api):
    pai = Categoria.objects.create(nome="Casa", slug="casa")
    api.post(URL_CATEGORIAS, {"name": "Canecas"}, format="json")
    filha = api.post(URL_CATEGORIAS, {"name": "Canecas", "parent": pai.pk}, format="json")
    assert filha.status_code == 201
    assert filha.json()["slug"] == "canecas-2"
    assert filha.json()["parent"] == pai.pk
