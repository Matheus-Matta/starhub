"""Como cada campo JSON da loja aparece no admin (um tratamento por tipo).

Os nomes das chaves sao os do WooCommerce, porque e esse JSON que a API Woo
devolve ao ERP. Os rotulos sao em portugues, para quem opera a loja.
"""

from apps.core.json_widgets import ChaveValorTema, ImagensTema, ListaTema, ObjetoTema

# largura: colunas numa grade de 12 ("CEP | Endereco | Numero" = 3 + 7 + 2).
ENDERECO = [
    {"campo": "first_name", "rotulo": "Nome", "largura": 6, "placeholder": "Ana"},
    {"campo": "last_name", "rotulo": "Sobrenome", "largura": 6, "placeholder": "Silva"},
    {"campo": "company", "rotulo": "Empresa", "largura": 6, "placeholder": "Nome da empresa"},
    {"campo": "cpf", "rotulo": "CPF", "largura": 3, "placeholder": "000.000.000-00",
     "mascara": "cpf"},
    {"campo": "cnpj", "rotulo": "CNPJ", "largura": 3, "placeholder": "00.000.000/0000-00",
     "mascara": "cnpj"},
    {"campo": "postcode", "rotulo": "CEP", "largura": 3, "placeholder": "00000-000",
     "mascara": "cep"},
    {"campo": "address_1", "rotulo": "Endereco", "largura": 7, "placeholder": "Rua, avenida..."},
    {"campo": "number", "rotulo": "Numero", "largura": 2, "placeholder": "123"},
    {"campo": "address_2", "rotulo": "Complemento", "largura": 6,
     "placeholder": "Bloco, apto, fundos..."},
    {"campo": "neighborhood", "rotulo": "Bairro", "largura": 6, "placeholder": "Centro"},
    {"campo": "city", "rotulo": "Cidade", "largura": 6, "placeholder": "Recife"},
    {"campo": "state", "rotulo": "UF", "largura": 3, "placeholder": "PE", "mascara": "uf"},
    {"campo": "country", "rotulo": "Pais", "largura": 3, "placeholder": "BR", "mascara": "pais"},
    {"campo": "phone", "rotulo": "Telefone", "largura": 4, "placeholder": "(00) 00000-0000",
     "mascara": "telefone"},
]
COBRANCA = [
    *ENDERECO,
    {"campo": "email", "rotulo": "E-mail", "largura": 8, "placeholder": "nome@empresa.com.br"},
]

DIMENSOES = [
    {"campo": "length", "rotulo": "Comprimento (cm)", "tipo": "numero-texto"},
    {"campo": "width", "rotulo": "Largura (cm)", "tipo": "numero-texto"},
    {"campo": "height", "rotulo": "Altura (cm)", "tipo": "numero-texto"},
]

ATRIBUTOS = [
    {"campo": "name", "rotulo": "Atributo", "tipo": "texto", "placeholder": "Cor"},
    {"campo": "options", "rotulo": "Opcoes", "tipo": "tags"},
    {"campo": "visible", "rotulo": "Visivel", "tipo": "switch"},
    {"campo": "variation", "rotulo": "Variacao", "tipo": "switch"},
]
FRETE = [
    {"campo": "method_title", "rotulo": "Metodo", "tipo": "texto", "placeholder": "Sedex"},
    {"campo": "method_id", "rotulo": "Codigo", "tipo": "texto", "placeholder": "flat_rate"},
    {"campo": "total", "rotulo": "Valor (R$)", "tipo": "dinheiro"},
]
TAXAS = [
    {"campo": "name", "rotulo": "Taxa", "tipo": "texto", "placeholder": "Embalagem"},
    {"campo": "total", "rotulo": "Valor (R$)", "tipo": "dinheiro"},
]
CUPONS = [
    {"campo": "code", "rotulo": "Cupom", "tipo": "texto", "placeholder": "BLACKFRIDAY10"},
    {"campo": "discount", "rotulo": "Desconto (R$)", "tipo": "dinheiro"},
]


PRODUTO = {
    "atributos": ListaTema(ATRIBUTOS, com_id=False, botao="Adicionar atributo"),
    "metadados": ChaveValorTema(),
}
VARIANTE = {"dimensions": ObjetoTema(DIMENSOES, extras=False, colunas=3)}
CATEGORIA = {"imagem": ImagensTema(multiplas=False, pasta="categorias")}
CLIENTE = {"metadados": ChaveValorTema()}
PEDIDO = {
    **CLIENTE,
    "linhas_frete": ListaTema(FRETE, com_id=True, botao="Adicionar frete"),
    "linhas_taxa": ListaTema(TAXAS, com_id=True, botao="Adicionar taxa"),
    "linhas_cupom": ListaTema(CUPONS, com_id=True, botao="Adicionar cupom"),
}
