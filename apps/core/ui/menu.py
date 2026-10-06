"""Monta o menu lateral a partir do `available_apps` que o admin ja entrega.

Cada app vira uma SECAO (titulo + separador, sem abrir/fechar) e cada model um
item com icone proprio (settings.STARHUB_MENU_ICONES["app.model"]). Assim um
model novo registrado no admin aparece no menu sem mexer em template.
"""

from django.conf import settings
from django.urls import NoReverseMatch, reverse

ICONE_PADRAO = "folder"
# "marca:shopify" no STARHUB_MENU_ICONES: o item usa o logo da plataforma
# (static/starhub/img/marcas/<codigo>.svg ou a imagem de IMAGENS), o mesmo do badge.
PREFIXO_MARCA = "marca:"


def _item(nome, url, icone):
    item = {"nome": nome, "url": url, "icone": icone, "ativo": False, "marca": ""}
    if icone.startswith(PREFIXO_MARCA):
        from apps.core.admin_utils import marca_html

        item["marca"] = marca_html(icone.removeprefix(PREFIXO_MARCA))
        item["icone"] = ICONE_PADRAO  # sem o arquivo da marca, cai no icone comum
    return item


def _ativo(caminho, url):
    return bool(url) and caminho.startswith(url)


def _chave(app_label, modelo):
    classe = modelo.get("model")
    nome = classe._meta.model_name if classe else str(modelo.get("object_name", "")).lower()
    return f"{app_label}.{nome}"


def _paginas_extras(app_label):
    """(titulo, nome da url) ou (titulo, nome da url, icone); o icone aceita "marca:"."""
    paginas = []
    for titulo, nome_url, *icone in getattr(settings, "STARHUB_MENU_PAGINAS", {}).get(
            app_label, []):
        try:
            paginas.append(_item(titulo, reverse(nome_url), icone[0] if icone else ICONE_PADRAO))
        except NoReverseMatch:
            continue
    return paginas


def montar_menu(available_apps, caminho):
    icones = getattr(settings, "STARHUB_MENU_ICONES", {})
    secoes = []
    for app in available_apps or []:
        itens = [
            # Model movido de outro app (STARHUB_MENU_AGRUPAR) guarda o app de origem.
            _item(modelo["name"], modelo["admin_url"],
                  icones.get(_chave(modelo.get("app_label", app["app_label"]), modelo),
                             ICONE_PADRAO))
            for modelo in app["models"]
            if modelo.get("admin_url")
        ]
        itens += _paginas_extras(app["app_label"])
        # O item mais especifico ganha: /admin/loja/pedido/ nao acende "Pedido item".
        melhor = max(
            (item for item in itens if _ativo(caminho, item["url"])),
            key=lambda item: len(item["url"]),
            default=None,
        )
        if melhor:
            melhor["ativo"] = True
        if itens:
            secoes.append({"nome": app["name"], "rotulo": app["app_label"], "itens": itens})
    ordem = getattr(settings, "STARHUB_MENU_ORDEM", [])
    posicoes = {rotulo: indice for indice, rotulo in enumerate(ordem)}
    return sorted(secoes, key=lambda secao: posicoes.get(secao["rotulo"], len(ordem)))


def com_minha_conta(app_list, request):
    """Troca o item "Contas" por "Minha conta", que abre direto a conta do usuario.

    Fora o superusuario, a lista de contas tem uma linha so (a propria): o link
    direto poupa um clique. O superusuario mantem a lista, pois e la que cadastra
    contas novas, e ganha "Minha conta" ao lado.
    """
    conta_id = getattr(request.user, "account_id", None)
    if conta_id is None:
        return app_list
    for app in app_list:
        for posicao, modelo in enumerate(app["models"]):
            if not (_do_model(modelo, "account") and modelo.get("admin_url")):
                continue
            minha = {**modelo, "name": "Minha conta", "add_url": None,
                     "admin_url": reverse("admin:core_account_change", args=[conta_id])}
            if request.user.is_superuser:
                app["models"].insert(posicao + 1, minha)
            else:
                app["models"][posicao] = minha
            return app_list
    return app_list


def _do_model(modelo, nome):
    return str(modelo.get("object_name", "")).lower() == nome


def agrupar_apps(app_list, regras):
    """Move os models de um app (ou um model so) para a secao de outro.

        {"woo_api": "core"}                          # o app inteiro
        {"integracoes.execucaointegracao": "core"}  # so este model; o app fica com o resto

    Se o app de destino nao aparece (usuario sem permissao nele), o de origem
    fica onde esta: melhor mostrar a secao original do que sumir com o item.
    """
    por_rotulo = {app["app_label"]: app for app in app_list}
    for origem, destino in (regras or {}).items():
        rotulo, _, nome = origem.partition(".")
        if rotulo not in por_rotulo or destino not in por_rotulo:
            continue
        app = por_rotulo[rotulo]
        saem = [m for m in app["models"] if not nome or _do_model(m, nome)]
        movidos = [{**modelo, "app_label": rotulo} for modelo in saem]
        por_rotulo[destino]["models"] = sorted(
            por_rotulo[destino]["models"] + movidos, key=lambda modelo: str(modelo["name"])
        )
        app["models"] = [m for m in app["models"] if m not in saem]
        if not app["models"]:
            app_list = [a for a in app_list if a["app_label"] != rotulo]
    return app_list
