from urllib.parse import urljoin, urlsplit


def url_publica(configuracao, url):
    """URL que a loja consegue baixar; "" quando o hub nao tem endereco publico.

    O MEDIA local devolve "/media/...": a base e a URL publica dos webhooks, o
    endereco do hub que a loja ja alcanca.
    """
    url = (url or "").strip()
    if urlsplit(url).scheme in ("http", "https"):
        return url
    base = configuracao.url_webhook or ""
    return urljoin(base, url) if url and base else ""
