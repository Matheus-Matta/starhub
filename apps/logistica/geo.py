"""CEP -> coordenada e distancia por estrada, com APIs gratuitas.

- Coordenada do CEP: AwesomeAPI (cep.awesomeapi.com.br) e, se faltar, BrasilAPI v2.
  Guardada em CoordenadaCep: cada CEP e consultado uma vez so.
- Distancia: OSRM publico (router.project-osrm.org), rota de carro em metros. Se ele
  nao responder, linha reta (haversine) x FATOR_ESTRADA, e a cotacao avisa que e
  estimativa. O OSRM publico e de demonstracao: com muito volume, troque por um
  servidor proprio na constante ROTA.
"""

import json
import math
import urllib.parse
import urllib.request
from decimal import ROUND_HALF_UP, Decimal
from urllib.error import HTTPError, URLError

from apps.logistica.models import CoordenadaCep, DistanciaCep

TIMEOUT = 8  # segundos: a cotacao responde na hora, nao pode esperar API parada
# No checkout da Shopify (3 s no total) cada chamada externa tem bem menos.
TIMEOUT_CHECKOUT = 0.8
FONTES_CEP = (
    ("awesomeapi", "https://cep.awesomeapi.com.br/json/{cep}"),
    ("brasilapi", "https://brasilapi.com.br/api/cep/v2/{cep}"),
)
# CEP que as duas bases nao conhecem (ex.: o CEP geral 24400-000 da cidade): a
# coordenada sai da cidade (centro aproximado), pelo geocodificador da OpenStreetMap.
CIDADE = "https://nominatim.openstreetmap.org/search?{consulta}"
ROTA = ("https://router.project-osrm.org/route/v1/driving/"
        "{lng1},{lat1};{lng2},{lat2}?overview=false")
# Estrada nunca e reta: 1,3 e a media de desvio usada em logistica para estimar.
FATOR_ESTRADA = Decimal("1.3")
RAIO_TERRA_KM = 6371.0


class GeoErro(Exception):
    """CEP sem coordenada ou API fora: a mensagem vai para quem cotou."""


def _json(url, timeout=TIMEOUT):
    requisicao = urllib.request.Request(url, headers={"User-Agent": "StarHub/1.0"})
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            return json.loads(resposta.read().decode())
    except (HTTPError, URLError, TimeoutError, ValueError) as erro:
        raise GeoErro(str(erro)) from erro


def _da_fonte(nome, dados):
    if nome == "awesomeapi":
        lat, lng = dados.get("lat"), dados.get("lng")
    else:
        ponto = ((dados.get("location") or {}).get("coordinates")) or {}
        lat, lng = ponto.get("latitude"), ponto.get("longitude")
    if not lat or not lng:
        return None
    return Decimal(str(lat)), Decimal(str(lng))


def _da_cidade(cidade, uf, timeout):
    consulta = urllib.parse.urlencode({"city": cidade, "state": uf, "country": "Brasil",
                                       "format": "json", "limit": 1})
    achados = _json(CIDADE.format(consulta=consulta), timeout)
    if not achados:
        return None
    return Decimal(str(achados[0]["lat"])), Decimal(str(achados[0]["lon"]))


def coordenada(cep, timeout=TIMEOUT, cidade="", uf=""):
    """(latitude, longitude) do CEP; GeoErro se nenhuma fonte souber.

    `cidade`/`uf` (o checkout da Shopify manda) sao a reserva para CEP desconhecido.
    """
    guardada = CoordenadaCep.objects.filter(cep=cep).first()
    if guardada:
        return guardada.latitude, guardada.longitude
    motivos = []
    for nome, url in FONTES_CEP:
        try:
            ponto = _da_fonte(nome, _json(url.format(cep=cep), timeout))
        except GeoErro as erro:
            motivos.append(f"{nome}: {erro}")
            continue
        if ponto:
            CoordenadaCep.objects.update_or_create(
                cep=cep, defaults={"latitude": ponto[0], "longitude": ponto[1], "fonte": nome})
            return ponto
        motivos.append(f"{nome}: sem coordenada")
    if cidade:
        try:
            ponto = _da_cidade(cidade, uf, timeout)
        except (GeoErro, KeyError, IndexError, TypeError) as erro:
            ponto, motivos = None, [*motivos, f"cidade: {erro}"]
        if ponto:
            CoordenadaCep.objects.update_or_create(
                cep=cep, defaults={"latitude": ponto[0], "longitude": ponto[1],
                                   "fonte": "cidade"})
            return ponto
    raise GeoErro(f"Nao foi possivel localizar o CEP {cep} ({'; '.join(motivos)}).")


def linha_reta_km(origem, destino):
    lat1, lng1, lat2, lng2 = map(math.radians, map(float, (*origem, *destino)))
    meio = (math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return Decimal(str(2 * RAIO_TERRA_KM * math.asin(math.sqrt(meio))))


def distancia_km(origem, destino, timeout=TIMEOUT):
    """(km por estrada com 1 casa, True se veio da rota; False se e estimativa)."""
    url = ROTA.format(lat1=origem[0], lng1=origem[1], lat2=destino[0], lng2=destino[1])
    try:
        dados = _json(url, timeout)
        metros = Decimal(str(dados["routes"][0]["distance"]))
        exata, km = True, metros / 1000
    except (GeoErro, KeyError, IndexError, TypeError):
        exata, km = False, linha_reta_km(origem, destino) * FATOR_ESTRADA
    return km.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), exata


def km_entre_ceps(cep_origem, cep_destino, timeout=TIMEOUT, cidade="", uf=""):
    """(km, exata) entre dois CEPs; a rota ja consultada vem do banco, sem rede."""
    guardada = DistanciaCep.objects.filter(origem=cep_origem, destino=cep_destino).first()
    if guardada:
        return guardada.km, True
    destino = coordenada(cep_destino, timeout, cidade, uf)
    km, exata = distancia_km(coordenada(cep_origem, timeout), destino, timeout)
    if exata:
        DistanciaCep.objects.update_or_create(origem=cep_origem, destino=cep_destino,
                                              defaults={"km": km})
    return km, exata
