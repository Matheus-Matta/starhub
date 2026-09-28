"""Busca do header: procura o termo em todo model do admin que tem search_fields.

Reaproveita o ModelAdmin.get_search_results de cada model, entao a busca
global acha exatamente o que a caixa de busca da listagem acharia. Model novo
com search_fields entra sozinho, sem mexer aqui.
"""

from django.urls import NoReverseMatch, reverse
from django.utils.http import urlencode

TAMANHO_MINIMO = 2
ITENS_POR_GRUPO = 5


def _url(opts, tipo, *args):
    try:
        return reverse(f"admin:{opts.app_label}_{opts.model_name}_{tipo}", args=args)
    except NoReverseMatch:
        return None


def buscar(request, admin_site, termo):
    termo = (termo or "").strip()
    if len(termo) < TAMANHO_MINIMO:
        return []
    grupos = []
    # _registry e o dicionario model -> ModelAdmin do proprio site (API estavel na pratica).
    for modelo, model_admin in admin_site._registry.items():
        if not model_admin.search_fields or not model_admin.has_view_permission(request):
            continue
        qs, repetidos = model_admin.get_search_results(
            request, model_admin.get_queryset(request), termo
        )
        if repetidos:
            qs = qs.distinct()
        total = qs.count()
        if not total:
            continue
        opts = modelo._meta
        lista = _url(opts, "changelist")
        grupos.append({
            "titulo": str(opts.verbose_name_plural).capitalize(),
            "total": total,
            "url_todos": f"{lista}?{urlencode({'q': termo})}" if lista else None,
            "itens": [
                {"texto": str(obj), "url": _url(opts, "change", obj.pk)}
                for obj in qs[:ITENS_POR_GRUPO]
            ],
        })
    return sorted(grupos, key=lambda grupo: grupo["titulo"])
