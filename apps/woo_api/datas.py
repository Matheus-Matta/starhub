"""Datas como o WooCommerce entrega: sem fuso no texto.

`date_created` vem no horario da loja; `date_created_gmt` vem em UTC.
Ex.: 2026-09-27T10:00:00 (Sao Paulo) e 2026-09-27T13:00:00 (GMT).
"""

from datetime import UTC

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.woo_api.erros import parametro_invalido


def local(valor):
    if not valor:
        return None
    return timezone.localtime(valor).replace(tzinfo=None).isoformat(timespec="seconds")


def gmt(valor):
    if not valor:
        return None
    return valor.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def par(prefixo, valor):
    """{"date_x": local, "date_x_gmt": gmt} para montar a resposta."""
    return {prefixo: local(valor), f"{prefixo}_gmt": gmt(valor)}


def ler(valor, campo, em_gmt=False):
    """Le a data enviada pelo ERP. Sem fuso: horario da loja (ou UTC se em_gmt)."""
    if valor in (None, ""):
        return None
    texto = str(valor).strip().replace(" ", "T")
    data = parse_datetime(texto)
    if data is None and parse_date(texto):
        data = parse_datetime(f"{texto}T00:00:00")
    if data is None:
        raise parametro_invalido(campo, f"{campo} nao e uma data ISO 8601 valida.")
    if timezone.is_naive(data):
        fuso = UTC if em_gmt else timezone.get_current_timezone()
        data = timezone.make_aware(data, fuso)
    return data


def ler_do_corpo(dados, prefixo):
    """Aceita date_x ou date_x_gmt no corpo; o _gmt ganha se vierem os dois."""
    if dados.get(f"{prefixo}_gmt"):
        return ler(dados[f"{prefixo}_gmt"], f"{prefixo}_gmt", em_gmt=True)
    return ler(dados.get(prefixo), prefixo)
