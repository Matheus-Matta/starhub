"""Cotacao de frete no checkout da Shopify (CarrierService).

A Shopify manda o carrinho e o endereco a cada CEP digitado no checkout e espera no
maximo 3 s. Cada TabelaFrete ativa com "oferecer no checkout" vira uma opcao:

    {"service_name": "Entrega propria", "service_code": "HUB_3", "total_price": "3891",
     "currency": "BRL", "description": "Entrega em 2 dias uteis",
     "min_delivery_date": "2026-10-07 18:00:00 -0300", "max_delivery_date": ...}

total_price vai em centavos (texto). Tabela que nao atende o CEP (fora das faixas, longe
demais, CEP que ninguem localiza) simplesmente nao aparece. O codigo HUB_<id> volta no
pedido (shipping_lines[].code -> linhas_frete[].method_id): da para saber qual tabela.
"""

import time
from datetime import timedelta

from django.utils import timezone

from apps.logistica import geo
from apps.logistica.cotacao import FreteIndisponivel, cotar
from apps.logistica.models import TabelaFrete

PREFIXO = "HUB_"
# Folga sobre os 3 s da Shopify: depois disto, as tabelas que faltam ficam de fora
# (melhor mostrar as que ja sairam do que nenhuma).
ORCAMENTO_SEGUNDOS = 2.2


def dias_uteis(inicio, dias):
    """Data `dias` dias uteis depois de `inicio` (sabado e domingo nao contam)."""
    data = inicio
    while dias > 0:
        data += timedelta(days=1)
        if data.weekday() < 5:
            dias -= 1
    return data


def _entrega(prazo):
    quando = dias_uteis(timezone.localtime(), prazo).replace(hour=18, minute=0, second=0,
                                                              microsecond=0)
    return quando.strftime("%Y-%m-%d %H:%M:%S %z")


def _opcao(tabela, cotacao):
    prazo = cotacao.prazo_dias
    texto_prazo = "dia util" if prazo == 1 else "dias uteis"
    entrega = _entrega(prazo)
    return {
        "service_name": tabela.nome,
        "service_code": f"{PREFIXO}{tabela.pk}",
        "total_price": str(int(cotacao.valor * 100)),
        "currency": "BRL",
        "description": f"Entrega em {prazo} {texto_prazo}",
        "min_delivery_date": entrega,
        "max_delivery_date": entrega,
    }


def _destino(corpo):
    return (((corpo or {}).get("rate") or {}).get("destination")) or {}


def cep_de_destino(corpo):
    return str(_destino(corpo).get("postal_code") or "")


def opcoes_de_frete(corpo, relogio=time.monotonic):
    """Lista de rates para a resposta; vazia se nenhuma tabela atende o CEP."""
    cep, inicio, opcoes = cep_de_destino(corpo), relogio(), []
    destino = _destino(corpo)
    cidade, uf = str(destino.get("city") or ""), str(destino.get("province") or "")
    tabelas = TabelaFrete.objects.filter(active=True, no_checkout=True).prefetch_related(
        "faixas").order_by("nome")
    for tabela in tabelas:
        if relogio() - inicio > ORCAMENTO_SEGUNDOS:
            break
        try:
            cotacao = cotar(tabela, cep, geo.TIMEOUT_CHECKOUT, cidade, uf)
            opcoes.append(_opcao(tabela, cotacao))
        except FreteIndisponivel:
            continue
    return sorted(opcoes, key=lambda opcao: int(opcao["total_price"]))
