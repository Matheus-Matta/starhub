"""CEP -> coordenada e distancia por estrada: o motor de CEP do hub.

coordenada(cep) tenta, nesta ordem, ate achar (tudo dentro do `limite` do checkout):

1. o banco (CoordenadaCep): CEP ja visto nao vai a rede;
2. AwesomeAPI (coordenada do CEP, com retentativa);
3. endereco (ViaCEP, OpenCEP, BrasilAPI v1 em paralelo) -> a rua, com o bairro
   conferido (Photon, Nominatim em paralelo);
4. aproximados: BrasilAPI v2 (as vezes e o centro da cidade), centro do bairro, centro
   da cidade, o CEP vizinho ja conhecido (geo_local, sem rede), a cidade do checkout.

Ponto aproximado (4) fica guardado e marcado: a cotacao sai, e uma
tarefa refaz a busca com calma (tasks.refinar_cep). A distancia vem do OSRM (dois
servidores em paralelo); sem rota, linha reta x fator aprendido (geo_local.fator), e
a estimativa tambem fica guardada para o preco nao mudar de uma cotacao para outra.
"""

import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.utils import timezone

from apps.logistica import geo_fontes as fontes
from apps.logistica import geo_local
from apps.logistica.geo_rede import GeoErro, buscar, limite, primeiro  # noqa: F401
from apps.logistica.models import CoordenadaCep, DistanciaCep

logger = logging.getLogger(__name__)
TIMEOUT = 8  # segundos por chamada fora do checkout (tela de cotacao, refino)
# Teto de cada chamada no checkout da Shopify. Era 0,8 s e a primeira chamada a um CEP
# novo passa disso (BrasilAPI 2,5 s, Nominatim 1 s medidos): o CEP nao era localizado e
# a Shopify usava o backup rate (pedido #3186). O total vem de `limite` (shopify/frete).
TIMEOUT_CHECKOUT = 3.0
ROTAS = (
    "https://router.project-osrm.org/route/v1/driving/{lng1},{lat1};{lng2},{lat2}"
    "?overview=false",
    # Servidor OSRM da FOSSGIS (OpenStreetMap Alemanha): reserva do publico.
    "https://routing.openstreetmap.de/routed-car/route/v1/driving/{lng1},{lat1};"
    "{lng2},{lat2}?overview=false",
)
# CEP aproximado que o refino nao achou: tenta de novo no maximo uma vez por hora.
REFINO = timedelta(hours=1)
FATOR_ESTRADA = geo_local.FATOR_ESTRADA
linha_reta_km = geo_local.linha_reta_km


def _agendar(tarefa, *args):
    """Refino em segundo plano; fila fora do ar nao pode derrubar a cotacao."""
    if not getattr(settings, "STARHUB_REFINAR_CEP", True):
        return
    from apps.core.tarefas import enfileirar
    from apps.logistica import tasks

    try:
        enfileirar(getattr(tasks, tarefa), *args)
    except Exception:  # noqa: BLE001 - broker fora: o refino fica para a proxima cotacao
        logger.warning("Nao foi possivel agendar %s%s", tarefa, args, exc_info=True)


def _endereco(cep, teto):
    return primeiro([lambda s: fontes.viacep(cep, s), lambda s: fontes.opencep(cep, s),
                     lambda s: fontes.brasilapi_endereco(cep, s)], teto)


def _na_rua(endereco, teto):
    if not (endereco and endereco.rua and endereco.bairro):
        return None
    rua = f"{endereco.rua}, {endereco.bairro}, {endereco.cidade}, {endereco.uf}, Brasil"
    return primeiro([lambda s: fontes.photon(rua, s, endereco.cidade, endereco.bairro),
                     lambda s: fontes.nominatim(rua, s, endereco.cidade, endereco.bairro)],
                    teto)


def _no_centro(lugar, cidade, teto):
    return primeiro([lambda s: fontes.photon(lugar, s, cidade),
                     lambda s: fontes.nominatim(lugar, s, cidade)], teto)


def localizar(cep, teto=TIMEOUT, cidade="", uf="", so_exato=False):
    """Ponto do CEP pelas fontes externas e pelo vizinho conhecido; None se ninguem sabe.

    Ordem do mais preciso ao mais grosso; `so_exato` (refino) para antes dos aproximados.
    """
    ponto = primeiro([lambda s: fontes.awesome(cep, s)], teto)
    endereco = None if ponto else _endereco(cep, teto)
    ponto = ponto or _na_rua(endereco, teto)
    if so_exato or ponto:
        return ponto
    ponto = primeiro([lambda s: fontes.brasilapi(cep, s)], teto)
    if ponto is None and endereco:
        lugar = f"{endereco.cidade}, {endereco.uf}, Brasil"
        bairro = f"{endereco.bairro}, {lugar}" if endereco.bairro else None
        ponto = ((bairro and _no_centro(bairro, endereco.cidade, teto))
                 or _no_centro(lugar, endereco.cidade, teto))
    ponto = ponto or geo_local.vizinho(cep)
    if ponto is None and cidade:
        ponto = _no_centro(f"{cidade}, {uf}, Brasil", cidade, teto)
    return ponto


def coordenada(cep, timeout=TIMEOUT, cidade="", uf=""):
    """(latitude, longitude) do CEP; GeoErro so se nem o motor local souber."""
    guardada = CoordenadaCep.objects.filter(cep=cep).first()
    if guardada:
        if guardada.aproximada and guardada.consultado_em < timezone.now() - REFINO:
            guardada.save(update_fields=["consultado_em"])  # uma tentativa por periodo
            _agendar("refinar_cep", cep)
        return guardada.latitude, guardada.longitude
    try:
        ponto = localizar(cep, timeout, cidade, uf)
    except GeoErro:  # acabou o tempo do checkout no meio: ainda ha o motor local
        ponto = geo_local.vizinho(cep)
    if ponto is None:
        raise GeoErro(f"Nao foi possivel localizar o CEP {cep}: nenhuma fonte respondeu e "
                      "nao ha CEP vizinho conhecido.")
    CoordenadaCep.objects.update_or_create(cep=cep, defaults={
        "latitude": ponto.latitude, "longitude": ponto.longitude, "fonte": ponto.fonte[:30],
        "aproximada": ponto.aproximado})
    if ponto.aproximado:
        _agendar("refinar_cep", cep)
    return ponto.latitude, ponto.longitude


def _rota(origem, destino, teto):
    def servidor(url):
        def chamar(segundos):
            dados = buscar(url.format(lat1=origem[0], lng1=origem[1], lat2=destino[0],
                                      lng2=destino[1]), segundos)
            return Decimal(str(dados["routes"][0]["distance"])) / 1000
        return chamar

    return primeiro([servidor(url) for url in ROTAS], teto)


def distancia_km(origem, destino, timeout=TIMEOUT, fator=FATOR_ESTRADA):
    """(km por estrada com 1 casa, True se veio da rota; False se e estimativa)."""
    try:
        km = _rota(origem, destino, timeout)
    except GeoErro:
        km = None
    exata = km is not None
    if not exata:
        km = linha_reta_km(origem, destino) * fator
    return km.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), exata


def km_entre_ceps(cep_origem, cep_destino, timeout=TIMEOUT, cidade="", uf=""):
    """(km, exata) entre dois CEPs; a distancia ja calculada vem do banco, sem rede."""
    guardada = DistanciaCep.objects.filter(origem=cep_origem, destino=cep_destino).first()
    if guardada:
        return guardada.km, guardada.exata
    destino = coordenada(cep_destino, timeout, cidade, uf)
    origem = coordenada(cep_origem, timeout)
    km, exata = distancia_km(origem, destino, timeout, geo_local.fator(cep_origem, origem))
    DistanciaCep.objects.update_or_create(origem=cep_origem, destino=cep_destino,
                                          defaults={"km": km, "exata": exata})
    if not exata:
        _agendar("refinar_distancia", cep_origem, cep_destino)
    return km, exata
