"""Monta o menu lateral a partir do `available_apps` que o admin ja entrega.

Cada app vira uma SECAO (titulo + separador, sem abrir/fechar) e cada model um
item com icone proprio (settings.STARHUB_MENU_ICONES["app.model"]). Assim um
model novo registrado no admin aparece no menu sem mexer em template.
"""

from django.conf import settings
from django.urls import NoReverseMatch, reverse

ICONE_PADRAO = "folder"


def _ativo(caminho, url):
    return bool(url) and caminho.startswith(url)


def _chave(app_label, modelo):
    classe = modelo.get("model")
    nome = classe._meta.model_name if classe else str(modelo.get("object_name", "")).lower()
    return f"{app_label}.{nome}"


def _paginas_extras(app_label):
    paginas = []
    for titulo, nome_url in getattr(settings, "STARHUB_MENU_PAGINAS", {}).get(app_label, []):
        try:
            paginas.append({"nome": titulo, "url": reverse(nome_url), "icone": ICONE_PADRAO})
        except NoReverseMatch:
            continue
    return paginas


def montar_menu(available_apps, caminho):
    icones = getattr(settings, "STARHUB_MENU_ICONES", {})
    secoes = []
    for app in available_apps or []:
        itens = [
            {
                "nome": modelo["name"],
                "url": modelo["admin_url"],
                # Model movido de outro app (STARHUB_MENU_AGRUPAR) guarda o app de origem.
                "icone": icones.get(_chave(modelo.get("app_label", app["app_label"]), modelo),
                                    ICONE_PADRAO),
                "ativo": False,
            }
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
    return secoes


def agrupar_apps(app_list, regras):
    """Move os models de um app para a secao de outro ({"woo_api": "auth"}).

    Se o app de destino nao aparece (usuario sem permissao nele), o de origem
    fica onde esta: melhor mostrar a secao original do que sumir com o item.
    """
    por_rotulo = {app["app_label"]: app for app in app_list}
    for origem, destino in (regras or {}).items():
        if origem not in por_rotulo or destino not in por_rotulo:
            continue
        movidos = [{**modelo, "app_label": origem} for modelo in por_rotulo[origem]["models"]]
        por_rotulo[destino]["models"] = sorted(
            por_rotulo[destino]["models"] + movidos, key=lambda modelo: str(modelo["name"])
        )
        app_list = [app for app in app_list if app["app_label"] != origem]
    return app_list
