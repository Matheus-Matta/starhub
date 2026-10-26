"""Fontes externas de CEP: coordenada direta, endereco e geocodificacao conferida.

Cada funcao recebe os segundos que pode usar e devolve um Ponto (ou None se nao sabe).

- direta: AwesomeAPI traz latitude/longitude do CEP; a BrasilAPI v2 tambem, mas as
  vezes e o centro da cidade (por isso vale como aproximada);
- endereco: ViaCEP, OpenCEP e BrasilAPI v1 trazem rua, bairro e cidade (sem coordenada);
- geocodificacao: Photon e Nominatim transformam o endereco em ponto. So vale o ponto
  da cidade certa, e o da rua so com o bairro certo: "Rua das Tulipas, Rio de Janeiro"
  sem o bairro devolveu outra rua a 35 km (medido), o que daria frete errado.
"""

import unicodedata
import urllib.parse
from dataclasses import dataclass
from decimal import Decimal

from apps.logistica.geo_rede import buscar

AWESOME = "https://cep.awesomeapi.com.br/json/{cep}"
BRASILAPI_V2 = "https://brasilapi.com.br/api/cep/v2/{cep}"
VIACEP = "https://viacep.com.br/ws/{cep}/json/"
OPENCEP = "https://opencep.com/v1/{cep}"
BRASILAPI_V1 = "https://brasilapi.com.br/api/cep/v1/{cep}"
PHOTON = "https://photon.komoot.io/api/?{consulta}"
NOMINATIM = "https://nominatim.openstreetmap.org/search?{consulta}"


@dataclass(frozen=True)
class Ponto:
    latitude: Decimal
    longitude: Decimal
    fonte: str
    aproximado: bool = False  # centro do bairro/cidade ou CEP vizinho, nao o CEP em si


@dataclass(frozen=True)
class Endereco:
    rua: str
    bairro: str
    cidade: str
    uf: str


def _ponto(lat, lng, fonte, aproximado=False):
    if lat in (None, "") or lng in (None, ""):
        return None
    lat, lng = Decimal(str(lat)), Decimal(str(lng))
    # Fora do Brasil e lixo da fonte (ex.: 0,0): melhor tentar a proxima.
    if not (-34 <= lat <= 6 and -74 <= lng <= -34):
        return None
    return Ponto(lat, lng, fonte, aproximado)


def simples(texto):
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore")
    return " ".join(sem_acento.decode().casefold().split())


# Coordenada direta.

def awesome(cep, segundos):
    dados = buscar(AWESOME.format(cep=cep), segundos)
    return _ponto(dados.get("lat"), dados.get("lng"), "awesomeapi")


def brasilapi(cep, segundos):
    """Aproximado sempre: sem o ponto do CEP ela devolve o centro da cidade sem avisar
    (21941-806, Cidade Universitaria, saiu -22.90642/-43.18223, o Centro do Rio, a ~5 km;
    medido em 26/10/2026)."""
    dados = buscar(BRASILAPI_V2.format(cep=cep), segundos)
    ponto = ((dados.get("location") or {}).get("coordinates")) or {}
    return _ponto(ponto.get("latitude"), ponto.get("longitude"), "brasilapi", aproximado=True)


# Endereco do CEP.

def viacep(cep, segundos):
    dados = buscar(VIACEP.format(cep=cep), segundos)
    if dados.get("erro") or not dados.get("localidade"):
        return None
    return Endereco(dados.get("logradouro") or "", dados.get("bairro") or "",
                    dados["localidade"], dados.get("uf") or "")


def opencep(cep, segundos):
    dados = buscar(OPENCEP.format(cep=cep), segundos)
    if not dados.get("localidade"):
        return None
    return Endereco(dados.get("logradouro") or "", dados.get("bairro") or "",
                    dados["localidade"], dados.get("uf") or "")


def brasilapi_endereco(cep, segundos):
    dados = buscar(BRASILAPI_V1.format(cep=cep), segundos)
    if not dados.get("city"):
        return None
    return Endereco(dados.get("street") or "", dados.get("neighborhood") or "",
                    dados["city"], dados.get("state") or "")


# Geocodificacao (endereco -> ponto), so com cidade (e bairro, na rua) conferidos.

def _confere(achados, cidade, bairro):
    cidades = {simples(c) for c in achados["cidades"] if c}
    if simples(cidade) not in cidades:
        return False
    return not bairro or any(simples(bairro) in simples(b) or simples(b) in simples(bairro)
                             for b in achados["bairros"] if b)


def photon(texto, segundos, cidade, bairro=""):
    consulta = urllib.parse.urlencode({"q": texto, "limit": 3, "lang": "default"})
    for item in buscar(PHOTON.format(consulta=consulta), segundos).get("features") or []:
        props = item.get("properties") or {}
        achados = {"cidades": [props.get("city"), props.get("county")],
                   "bairros": [props.get("district"), props.get("locality"),
                               props.get("suburb"), props.get("name")]}
        if _confere(achados, cidade, bairro):
            lng, lat = (item.get("geometry") or {}).get("coordinates") or (None, None)
            return _ponto(lat, lng, "photon", aproximado=not bairro)
    return None


def nominatim(texto, segundos, cidade, bairro=""):
    consulta = urllib.parse.urlencode({"q": texto, "countrycodes": "br", "format": "json",
                                       "addressdetails": 1, "limit": 3})
    for item in buscar(NOMINATIM.format(consulta=consulta), segundos) or []:
        endereco = item.get("address") or {}
        achados = {"cidades": [endereco.get(c) for c in ("city", "town", "municipality",
                                                         "village")],
                   "bairros": [endereco.get(b) for b in ("suburb", "neighbourhood", "quarter",
                                                         "city_district")]}
        if _confere(achados, cidade, bairro):
            return _ponto(item.get("lat"), item.get("lon"), "nominatim",
                          aproximado=not bairro)
    return None
