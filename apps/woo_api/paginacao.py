"""Paginacao do WordPress: ?page=&per_page=&offset= e os cabecalhos X-WP-Total,
X-WP-TotalPages e Link. O ERP percorre as paginas lendo esses cabecalhos."""

import math
from urllib.parse import urlencode

from apps.woo_api.erros import parametro_invalido

POR_PAGINA_PADRAO = 10
POR_PAGINA_MAXIMO = 100


def _inteiro(params, nome, padrao, minimo, maximo=None):
    bruto = params.get(nome)
    if bruto in (None, ""):
        return padrao
    try:
        valor = int(bruto)
    except (TypeError, ValueError) as erro:
        raise parametro_invalido(nome, f"{nome} nao e do tipo integer.") from erro
    if valor < minimo or (maximo is not None and valor > maximo):
        faixa = f"entre {minimo} e {maximo}" if maximo else f"maior ou igual a {minimo}"
        raise parametro_invalido(nome, f"{nome} deve estar {faixa} (inclusive).")
    return valor


def _link(request, pagina):
    params = request.query_params.copy()
    params["page"] = pagina
    for secreto in ("consumer_key", "consumer_secret"):
        params.pop(secreto, None)
    return request.build_absolute_uri(f"{request.path}?{urlencode(params, doseq=True)}")


def paginar(request, queryset):
    """Devolve (lista_da_pagina, cabecalhos)."""
    params = request.query_params
    por_pagina = _inteiro(params, "per_page", POR_PAGINA_PADRAO, 1, POR_PAGINA_MAXIMO)
    pagina = _inteiro(params, "page", 1, 1)
    deslocamento = _inteiro(params, "offset", None, 0)
    inicio = deslocamento if deslocamento is not None else (pagina - 1) * por_pagina

    total = queryset.count()
    total_paginas = math.ceil(total / por_pagina) if total else 0
    itens = list(queryset[inicio : inicio + por_pagina])

    cabecalhos = {"X-WP-Total": str(total), "X-WP-TotalPages": str(total_paginas)}
    links = []
    if pagina > 1:
        links.append(f'<{_link(request, pagina - 1)}>; rel="prev"')
    if pagina < total_paginas:
        links.append(f'<{_link(request, pagina + 1)}>; rel="next"')
    if links:
        cabecalhos["Link"] = ", ".join(links)
    return itens, cabecalhos
