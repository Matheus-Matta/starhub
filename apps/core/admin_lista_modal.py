"""Lista de filhos com botoes que abrem o formulario num modal (ex.: variantes).

A tela (template do ModelAdmin) marca os botoes com atributos data-, e o
static/starhub/js/modal-lista.js faz o resto:

    data-modal-url="/admin/.../add/?produto=12&_popup=1"  abre este form no modal
    data-modal-titulo="Editar variante"                   titulo do modal
    data-modal-chave="variantes"                          nome para abrir sozinho depois
    data-modal-salvar-antes                               pai ainda nao salvo (criacao)

Na CRIACAO o pai ainda nao existe para o filho apontar: o botao salva o pai
("Salvar e continuar" + _abrir_modal=<chave>), a resposta volta para a edicao com
?abrir_modal=<chave> (redirecionar_para_modal) e o botao dessa chave abre sozinho.

No modal aberto pela lista, o pai ja esta decidido: o ModelAdmin do filho declara
`pai_da_lista = "produto"` e o form esconde esse campo e a secao "Conta" (a conta
vem do pai). Ver aberto_pelo_pai.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib.admin.options import IS_POPUP_VAR
from django.urls import reverse

CAMPO_POST = "_abrir_modal"
PARAMETRO = "abrir_modal"


def url_popup(nome_url, *args, **params):
    """URL do admin pronta para o modal: url_popup("admin:loja_x_add", produto=12)."""
    return f"{reverse(nome_url, args=args)}?{urlencode({**params, '_popup': 1})}"


def aberto_pelo_pai(model_admin, request, obj=None):
    """O form esta no modal da lista do pai (variante aberta na pagina do produto)?

    Edicao: o registro ja tem o pai. Criacao: o pai veio na URL (?produto=12). O
    POST vai para a mesma URL, entao o GET continua com os parametros.
    """
    pai = getattr(model_admin, "pai_da_lista", None)
    return bool(pai) and IS_POPUP_VAR in request.GET and (obj is not None or pai in request.GET)


def redirecionar_para_modal(request, resposta):
    """Depois de salvar o pai pelo botao da lista: a edicao abre com o modal."""
    chave = request.POST.get(CAMPO_POST, "")
    destino = resposta.get("Location") if resposta.status_code == 302 else None
    # So um nome simples ("variantes"): o valor volta na URL, nada de texto livre.
    if not destino or not re.fullmatch(r"[\w-]{1,60}", chave):
        return resposta
    partes = urlsplit(destino)
    consulta = [*parse_qsl(partes.query), (PARAMETRO, chave)]
    resposta["Location"] = urlunsplit(partes._replace(query=urlencode(consulta)))
    return resposta
