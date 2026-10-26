"""Cotacao de frete no checkout da Shopify (CarrierService).

A Shopify manda o carrinho e o endereco a cada CEP digitado no checkout e espera ate
10 s (loja com menos de 1500 pedidos de cotacao por minuto; 5 s ate 3000, 3 s acima:
doc DeliveryCarrierService). Erro ou tempo estourado = backup rate. Cada TabelaFrete
ativa com "oferecer no checkout" vira uma opcao:

    {"service_name": "Entrega propria", "service_code": "HUB_3", "total_price": "3891",
     "currency": "BRL", "description": "Entrega em 2 dias uteis",
     "min_delivery_date": "2026-10-07 18:00:00 -0300", "max_delivery_date": ...}

Quando a loja oculta o prazo, a descricao obrigatoria continua presente, mas sem os
dias; somente as duas datas de entrega deixam de ser enviadas.
total_price vai em centavos (texto). Tabela que nao atende o CEP (fora das faixas, longe
demais, CEP que ninguem localiza) simplesmente nao aparece. O codigo HUB_<id> volta no
pedido (shipping_lines[].code -> linhas_frete[].method_id): da para saber qual tabela.
"""

import logging
import time
from datetime import timedelta

from django.utils import timezone

from apps.logistica import geo
from apps.logistica.cotacao import FreteIndisponivel, cotar
from apps.logistica.models import TabelaFrete

logger = logging.getLogger(__name__)
PREFIXO = "HUB_"
# Tempo total das APIs externas (CEP, rota) na cotacao, com folga sobre os 10 s da
# Shopify. Depois de ORCAMENTO_SEGUNDOS nenhuma tabela nova comeca (melhor mostrar as
# que ja sairam do que nenhuma).
LIMITE_SEGUNDOS = 7.0
ORCAMENTO_SEGUNDOS = 6.0


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


def _opcao(tabela, cotacao, exibir_prazo=True):
    prazo = cotacao.prazo_dias
    opcao = {
        "service_name": tabela.nome,
        "service_code": f"{PREFIXO}{tabela.pk}",
        "total_price": str(int(cotacao.valor * 100)),
        "currency": "BRL",
        # A Shopify descarta a tarifa sem description e usa o backup rate, mesmo
        # quando o endpoint respondeu 200. O switch esconde o prazo, nao este campo.
        "description": "Frete calculado pelo StarHub",
    }
    if exibir_prazo:
        texto_prazo = "dia util" if prazo == 1 else "dias uteis"
        entrega = _entrega(prazo)
        opcao.update({
            "description": f"Entrega em {prazo} {texto_prazo}",
            "min_delivery_date": entrega,
            "max_delivery_date": entrega,
        })
    return opcao


def _destino(corpo):
    return (((corpo or {}).get("rate") or {}).get("destination")) or {}


def cep_de_destino(corpo):
    return str(_destino(corpo).get("postal_code") or "")


def opcoes_de_frete(corpo, relogio=time.monotonic, exibir_prazo=True):
    """Lista de rates para a resposta; vazia se nenhuma tabela atende o CEP."""
    cep, inicio, opcoes = cep_de_destino(corpo), relogio(), []
    destino = _destino(corpo)
    cidade, uf = str(destino.get("city") or ""), str(destino.get("province") or "")
    tabelas = TabelaFrete.objects.filter(active=True, no_checkout=True).prefetch_related(
        "faixas").order_by("nome")
    with geo.limite(LIMITE_SEGUNDOS):
        for tabela in tabelas:
            if relogio() - inicio > ORCAMENTO_SEGUNDOS:
                logger.warning("Frete do CEP %s: tempo esgotado antes da tabela %s", cep,
                               tabela.nome)
                break
            try:
                cotacao = cotar(tabela, cep, geo.TIMEOUT_CHECKOUT, cidade, uf)
                opcoes.append(_opcao(tabela, cotacao, exibir_prazo))
            except FreteIndisponivel as motivo:
                # Rastro do "por que nao saiu frete": sem isto o backup rate na Shopify
                # nao deixava pista nenhuma no hub.
                logger.warning("Frete do CEP %s sem a tabela %s: %s", cep, tabela.nome, motivo)
            except Exception:  # noqa: BLE001 - erro inesperado numa tabela nao pode virar
                # 500 (backup rate na Shopify) nem tirar o frete das outras tabelas.
                logger.exception("Frete do CEP %s: erro na tabela %s", cep, tabela.nome)
    return sorted(opcoes, key=lambda opcao: int(opcao["total_price"]))
