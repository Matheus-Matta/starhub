"""Dados de demonstracao para testar o sistema: python manage.py gerar_demo.

Tudo o que nasce aqui leva a marca MARCA nos metadados (ou um prefixo, nos models
sem metadados: conta e usuario), e so o que tem a marca e apagado pelo --limpar.
Imagens: static/starhub/img/demos (demo1.png, demo2.png), por URL do static, sem
copiar arquivo para o media.
"""

from django.templatetags.static import static

MARCA_CHAVE = "_demo"
PREFIXO_CONTA = "demo-loja-"
SENHA_USUARIOS = "demo@12345"
DOMINIO_EMAIL = "demo.starhub.test"


def marca():
    """metadados (formato meta_data do Woo) de todo registro demo."""
    return [{"id": 1, "key": MARCA_CHAVE, "value": "gerar_demo"}]


def eh_demo(obj):
    return any(
        isinstance(item, dict) and item.get("key") == MARCA_CHAVE for item in obj.metadados or []
    )


def prefixo_usuario(conta):
    return f"demo.{conta.slug}."


def imagem(indice):
    """demo1/demo2 alternando, no formato de imagem do Woo (categoria, galeria)."""
    nome = f"demo{indice % 2 + 1}"
    return {"src": static(f"starhub/img/demos/{nome}.png"), "name": nome, "alt": ""}


def nome_n(nomes, indice):
    """Com --quantidade maior que a lista, repete os nomes com numero: "Vendas 2"."""
    base = nomes[indice % len(nomes)]
    return base if indice < len(nomes) else f"{base} {indice // len(nomes) + 1}"
