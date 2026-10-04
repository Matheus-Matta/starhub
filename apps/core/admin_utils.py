"""Pecas de apresentacao reaproveitadas pelos ModelAdmin de todos os apps."""

import re
from functools import lru_cache
from pathlib import Path

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.core.ui.formatos import moeda, tom_status


def badge(texto, tom="secondary"):
    return format_html('<span class="badge badge-{}">{}</span>', tom, texto)


def badge_status(valor, rotulo):
    """Badge colorida pela chave do status (ex.: "completed") com o rotulo traduzido."""
    return badge(rotulo, tom_status(valor))


def valor_moeda(valor):
    return format_html('<span class="nowrap">{}</span>', moeda(valor))


def imagem_principal(imagens):
    """Devolve a primeira URL valida da galeria Woo do produto."""
    if not isinstance(imagens, list):
        return ""
    return next(
        (item.get("src", "") for item in imagens if isinstance(item, dict) and item.get("src")),
        "",
    )


def iniciais_de(texto):
    partes = str(texto or "?").strip().split()
    return "".join(parte[0] for parte in partes[:2]).upper() or "?"



def acoes_da_linha(obj, conteudo="", rotulo="Ver detalhes"):
    """Coluna "Acoes": "+" que abre `conteudo` (HTML) abaixo da linha e o lapis da edicao."""
    opts = obj._meta
    return render_to_string("components/linha_detalhe.html", {
        "conteudo": conteudo, "rotulo": rotulo,
        "url_editar": reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk]),
    })


# Icones das marcas: Simple Icons (https://simpleicons.org, CC0), baixados para
# static/starhub/img/marcas com a cor oficial. Plataforma que nao esta la (Mercado
# Livre, Magalu, Amazon) usa o icone de loja; as internas, um icone do sprite.
MARCAS = {"shopify": "#7AB55C", "woocommerce": "#96588A", "shopee": "#EE4D2D"}
ICONES = {"api": "plug", "import": "archive"}
# O proprio StarHub usa o simbolo da marca (o mesmo do favicon).
IMAGENS = {"starhub": "starhub/img/marca-64.png"}


@lru_cache(maxsize=None)
def svg_da_marca(codigo):
    """SVG do Simple Icons pronto para embutir (sem <title>, na cor da marca)."""
    arquivo = finders.find(f"starhub/img/marcas/{codigo}.svg")
    if codigo not in MARCAS or not arquivo:
        return ""
    svg = re.sub(r"<title>.*?</title>", "", Path(arquivo).read_text(encoding="utf-8"))
    # Classe propria: o .icon do tema e de traco (fill: none) e apagaria o logo.
    return mark_safe(svg.replace('role="img" ', "").replace(
        "<svg ", f'<svg class="sh-marca" aria-hidden="true" fill="{MARCAS[codigo]}" ', 1
    ))


def badge_origem(codigo, nome):
    """Badge neutro da origem: icone da plataforma + nome ("Shopify")."""
    return render_to_string("components/badge_origem.html", {
        "nome": nome, "svg": svg_da_marca(codigo), "icone": ICONES.get(codigo, "store"),
        "imagem": static(IMAGENS[codigo]) if codigo in IMAGENS else "",
    })


def na_listagem(request):
    """A requisicao e a listagem (changelist)? Prefetch so da listagem fica fora da
    edicao: la o cache ficaria velho depois de o inline salvar (ex.: total do pedido)."""
    rota = getattr(request, "resolver_match", None)
    return bool(rota and rota.url_name and rota.url_name.endswith("_changelist"))
