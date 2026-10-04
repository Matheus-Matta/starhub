"""CEP -> coordenada e distancia, com as respostas reais das APIs gratuitas (sem rede)."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.logistica import geo
from apps.logistica.models import CoordenadaCep

pytestmark = pytest.mark.django_db
# Formatos copiados das respostas de verdade (CEP 01001-000, Praca da Se).
AWESOME = {"cep": "01001000", "lat": "-23.5500806", "lng": "-46.6340827", "city": "Sao Paulo"}
BRASILAPI = {"cep": "01001000", "location": {"type": "Point", "coordinates": {
    "longitude": "-46.633081", "latitude": "-23.5503898"}}}
SE = (Decimal("-23.5500806"), Decimal("-46.6340827"))
PIO_X = (Decimal("-22.9004"), Decimal("-43.178"))


def _respostas(*respostas):
    fila = list(respostas)

    def falsa(url, timeout=None):
        resposta = fila.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    return patch.object(geo, "_json", side_effect=falsa)


def test_coordenada_vem_da_awesomeapi_e_fica_guardada():
    """Cada CEP e consultado uma vez: API gratuita tem limite de uso."""
    with _respostas(AWESOME) as api:
        assert geo.coordenada("01001000") == SE
        assert geo.coordenada("01001000") == SE
    assert api.call_count == 1
    assert CoordenadaCep.objects.get(cep="01001000").fonte == "awesomeapi"


def test_sem_awesomeapi_usa_a_brasilapi():
    with _respostas(geo.GeoErro("HTTP 429"), BRASILAPI):
        assert geo.coordenada("01001000") == (Decimal("-23.5503898"), Decimal("-46.633081"))
    assert CoordenadaCep.objects.get().fonte == "brasilapi"


def test_cep_que_ninguem_localiza_explica_o_motivo():
    with _respostas({"cep": "99999999"}, {"location": {}}), \
            pytest.raises(geo.GeoErro, match="99999999.*sem coordenada"):
        geo.coordenada("99999999")
    assert not CoordenadaCep.objects.exists()


def test_distancia_pela_rota_de_carro_do_osrm():
    with _respostas({"code": "Ok", "routes": [{"distance": 432843.2}]}):
        assert geo.distancia_km(SE, PIO_X) == (Decimal("432.8"), True)


def test_rota_fora_do_ar_estima_pela_linha_reta_e_avisa():
    """Sem rota a cotacao ainda sai, mas marcada como estimativa (False)."""
    with _respostas(geo.GeoErro("timeout")):
        km, exata = geo.distancia_km(SE, PIO_X)
    reta = geo.linha_reta_km(SE, PIO_X)
    assert not exata
    assert Decimal("355") < reta < Decimal("365")  # Se -> Pio X em linha reta ~360 km
    assert km == (reta * geo.FATOR_ESTRADA).quantize(Decimal("0.1"))


def test_distancia_entre_ceps_fica_guardada_e_a_estimativa_nao():
    """No checkout (3 s) a rota ja consultada nao pode ir para a rede de novo."""
    from apps.logistica.models import DistanciaCep

    CoordenadaCep.objects.create(cep="01001000", latitude=SE[0], longitude=SE[1], fonte="t")
    CoordenadaCep.objects.create(cep="20040020", latitude=PIO_X[0], longitude=PIO_X[1], fonte="t")
    with _respostas(geo.GeoErro("timeout")):
        assert geo.km_entre_ceps("01001000", "20040020")[1] is False
    assert not DistanciaCep.objects.exists()
    with _respostas({"code": "Ok", "routes": [{"distance": 432843.2}]}) as api:
        assert geo.km_entre_ceps("01001000", "20040020") == (Decimal("432.8"), True)
        assert geo.km_entre_ceps("01001000", "20040020") == (Decimal("432.8"), True)
    assert api.call_count == 1


def test_cep_que_as_bases_nao_conhecem_sai_pela_cidade():
    """24400-000 (CEP geral de Sao Goncalo) da 404 nas duas bases: o checkout manda a
    cidade, e a coordenada aproximada dela evita sumir com a opcao de frete."""
    cidade = [{"lat": "-22.8216350", "lon": "-42.9956797"}]
    with _respostas(geo.GeoErro("HTTP 404"), geo.GeoErro("HTTP 404"), cidade) as api:
        ponto = geo.coordenada("24400000", cidade="Sao Goncalo", uf="RJ")
    assert ponto == (Decimal("-22.8216350"), Decimal("-42.9956797"))
    assert "Sao+Goncalo" in api.call_args.args[0] and "state=RJ" in api.call_args.args[0]
    assert CoordenadaCep.objects.get(cep="24400000").fonte == "cidade"
    with _respostas(geo.GeoErro("404"), geo.GeoErro("404")), pytest.raises(geo.GeoErro):
        geo.coordenada("24400001")  # sem cidade, continua sem frete por distancia
