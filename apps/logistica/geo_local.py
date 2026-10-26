"""Motor de CEP do proprio hub: responde sem rede com o que ele ja aprendeu.

- vizinho(cep): o CEP conhecido mais proximo no numero, com o mesmo comeco (5 digitos
  e depois 3). CEP e distribuido por regiao: 21941-806 e 21941-590 ficam a poucos km.
- fator(origem): quanto a estrada desvia da linha reta para esta origem, aprendido das
  rotas reais ja guardadas (mediana). Sem rotas suficientes, o 1,3 de mercado.

Os dois so entram quando as APIs externas nao respondem: nunca trocam um dado exato.
"""

import math
from decimal import Decimal
from statistics import median

from apps.logistica.geo_fontes import Ponto
from apps.logistica.models import CoordenadaCep, DistanciaCep

FATOR_ESTRADA = Decimal("1.3")
FATOR_MINIMO, FATOR_MAXIMO = Decimal("1.05"), Decimal("2.0")
AMOSTRAS_MINIMAS = 5
RAIO_TERRA_KM = 6371.0


def linha_reta_km(origem, destino):
    lat1, lng1, lat2, lng2 = map(math.radians, map(float, (*origem, *destino)))
    meio = (math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return Decimal(str(2 * RAIO_TERRA_KM * math.asin(math.sqrt(meio))))


def vizinho(cep):
    """Ponto aproximado do CEP pelo vizinho conhecido; None se nao ha nenhum perto."""
    numero = int(cep)
    for digitos in (5, 3):
        candidatos = list(CoordenadaCep.objects.filter(
            cep__startswith=cep[:digitos], aproximada=False).exclude(cep=cep)
            .values_list("cep", "latitude", "longitude")[:500])
        if candidatos:
            perto = min(candidatos, key=lambda c: abs(int(c[0]) - numero))
            return Ponto(perto[1], perto[2], f"vizinho {perto[0]}", aproximado=True)
    return None


def fator(origem_cep, origem):
    """Desvio da estrada para esta origem, aprendido; FATOR_ESTRADA sem amostras."""
    rotas = dict(DistanciaCep.objects.filter(origem=origem_cep, exata=True)
                 .values_list("destino", "km")[:300])
    pontos = CoordenadaCep.objects.filter(cep__in=list(rotas), aproximada=False)
    razoes = []
    for ponto in pontos:
        reta = linha_reta_km(origem, (ponto.latitude, ponto.longitude))
        if reta >= 1:  # muito perto, a razao vira ruido
            razoes.append(Decimal(rotas[ponto.cep]) / reta)
    if len(razoes) < AMOSTRAS_MINIMAS:
        return FATOR_ESTRADA
    return min(max(Decimal(str(median(razoes))), FATOR_MINIMO), FATOR_MAXIMO)
