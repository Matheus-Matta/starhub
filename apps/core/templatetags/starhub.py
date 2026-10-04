"""Tags do tema StarHub. Carregada como builtin (settings.TEMPLATES), sem {% load %}."""

from pathlib import Path

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.utils.html import format_html

from apps.core.ui import componentes, formatos, formulario, listagem, menu

register = template.Library()

register.tag("componente", componentes.componente)
register.tag("slot", componentes.slot)
register.filter("moeda", formatos.moeda)
register.filter("tom_status", formatos.tom_status)
register.filter("filtros_ativos", listagem.filtros_ativos)
register.filter("campo_largo", formulario.campo_largo)


@register.simple_tag
def url_sprite():
    """URL do sprite com a versao (data do arquivo): icone novo no sprite chega ao
    navegador na hora, em vez de ele seguir com a copia antiga (sem o icone) em cache."""
    arquivo = finders.find("starhub/img/icones.svg")
    versao = int(Path(arquivo).stat().st_mtime) if arquivo else 0
    return f"{static('starhub/img/icones.svg')}?v={versao}"


@register.simple_tag
def icone(nome, classe=""):
    """Icone do sprite (lucide). Ex.: {% icone "package" "icon-lg" %}."""
    sprite = url_sprite()
    return format_html(
        '<svg class="icon {}" aria-hidden="true" focusable="false">'
        '<use href="{}#{}"></use></svg>',
        classe,
        sprite,
        nome,
    )


@register.simple_tag(takes_context=True)
def menu_lateral(context):
    request = context.get("request")
    caminho = request.path if request else ""
    return menu.montar_menu(context.get("available_apps"), caminho)


@register.filter
def iniciais(usuario):
    """Iniciais para o avatar do menu do usuario: "Matheus Eduardo" -> "ME"."""
    nome = (usuario.get_full_name() or usuario.get_username() or "?").split()
    return "".join(parte[0] for parte in nome[:2]).upper()
