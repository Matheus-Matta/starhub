"""Pecas de apresentacao reaproveitadas pelos ModelAdmin de todos os apps."""

from django.utils.html import format_html

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

