"""Motor de CEP: fontes em camadas, motor local e rede (respostas reais copiadas, sem rede)."""

import time
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.logistica import geo, geo_rede
from apps.logistica.models import CoordenadaCep, DistanciaCep

pytestmark = pytest.mark.django_db
SE = (Decimal("-23.5500806"), Decimal("-46.6340827"))
PIO_X = (Decimal("-22.9004"), Decimal("-43.178"))
# Respostas de verdade para o CEP do pedido #3186 (21941-806, Rua das Tulipas).
VIACEP = {"cep": "21941-806", "logradouro": "Rua das Tulipas", "bairro": "Cidade Universitária",
          "localidade": "Rio de Janeiro", "uf": "RJ"}
PHOTON_RUA = {"features": [{"geometry": {"coordinates": [-43.2177, -22.8694]}, "properties": {
    "name": "Rua das Tulipas", "district": "Cidade Universitária", "city": "Rio de Janeiro"}}]}
# A outra Rua das Tulipas (zona oeste, ~35 km): a Nominatim devolveu esta sem o bairro.
NOMINATIM_ERRADA = [{"lat": "-22.9380960", "lon": "-43.5677566", "address": {
    "suburb": "Campo Grande", "city": "Rio de Janeiro"}}]
NOMINATIM_BAIRRO = [{"lat": "-22.8580", "lon": "-43.2280", "address": {
    "suburb": "Cidade Universitária", "city": "Rio de Janeiro"}}]


def _api(**respostas):
    """Falso por URL: {"awesomeapi": {...}, "viacep": GeoErro(...)}; o resto falha."""
    def falsa(url, timeout):
        for trecho, resposta in respostas.items():
            if trecho in url:
                if callable(resposta) and not isinstance(resposta, Exception):
                    resposta = resposta(url)
                if isinstance(resposta, Exception):
                    raise resposta
                return resposta
        raise geo.GeoErro(f"fora do ar: {url}")

    return patch.object(geo_rede, "_json", side_effect=falsa)


def test_coordenada_direta_fica_guardada_e_nao_vai_a_rede_de_novo():
    with _api(awesomeapi={"lat": "-23.5500806", "lng": "-46.6340827"}) as api:
        assert geo.coordenada("01001000") == SE
        chamadas = api.call_count
        assert geo.coordenada("01001000") == SE
    assert api.call_count == chamadas
    guardada = CoordenadaCep.objects.get(cep="01001000")
    assert (guardada.fonte, guardada.aproximada) == ("awesomeapi", False)


def test_fonte_de_endereco_lenta_nao_segura_a_que_responde():
    """ViaCEP, OpenCEP e BrasilAPI v1 rodam juntas: a lenta nao atrasa a outra."""
    def lenta(url):
        time.sleep(2)
        return VIACEP

    opencep = {"logradouro": "Rua das Tulipas", "bairro": "Cidade Universitária",
               "localidade": "Rio de Janeiro", "uf": "RJ"}
    inicio = time.monotonic()
    with _api(viacep=lenta, opencep=opencep, photon=PHOTON_RUA):
        assert geo.coordenada("21941806") == (Decimal("-22.8694"), Decimal("-43.2177"))
    assert time.monotonic() - inicio < 1.5


def test_brasilapi_vale_so_como_aproximada_porque_as_vezes_e_o_centro_da_cidade(settings):
    """21941-806 na BrasilAPI v2: -22.90642/-43.18223, o Centro do Rio (medido). O ponto
    da rua (endereco) ganha dela; sozinha, ela vale como aproximada e agenda o refino."""
    brasilapi = {"location": {"coordinates": {"latitude": "-22.90642",
                                              "longitude": "-43.18223"}}}
    with _api(**{"api/cep/v2": brasilapi}, viacep=VIACEP, photon=PHOTON_RUA):
        assert geo.coordenada("21941806") == (Decimal("-22.8694"), Decimal("-43.2177"))
    CoordenadaCep.objects.all().delete()
    settings.STARHUB_REFINAR_CEP = True
    agendadas = []
    enfileirar = patch("apps.core.tarefas.enfileirar", lambda t, *a: agendadas.append(a))
    with _api(**{"api/cep/v2": brasilapi}), enfileirar:
        assert geo.coordenada("21941806") == (Decimal("-22.90642"), Decimal("-43.18223"))
    assert CoordenadaCep.objects.get().aproximada and agendadas == [("21941806",)]


def test_sem_coordenada_direta_usa_o_endereco_com_o_bairro_conferido():
    """Pedido #3186: ViaCEP da a rua e o bairro; o ponto e o da rua certa."""
    with _api(viacep=VIACEP, photon=PHOTON_RUA, nominatim=NOMINATIM_ERRADA):
        assert geo.coordenada("21941806") == (Decimal("-22.8694"), Decimal("-43.2177"))
    assert CoordenadaCep.objects.get().aproximada is False


def test_rua_de_outro_bairro_e_recusada_e_vale_o_centro_do_bairro(settings):
    """A outra Rua das Tulipas daria frete de 35 km a mais: melhor o centro do bairro."""
    settings.STARHUB_REFINAR_CEP = True
    agendadas = []
    with _api(viacep=VIACEP, nominatim=lambda url: (
            NOMINATIM_BAIRRO if "Tulipas" not in url else NOMINATIM_ERRADA)), \
            patch("apps.core.tarefas.enfileirar", lambda t, *a: agendadas.append(a)):
        assert geo.coordenada("21941806") == (Decimal("-22.8580"), Decimal("-43.2280"))
    assert CoordenadaCep.objects.get().aproximada is True
    assert agendadas == [("21941806",)], "aproximado: o refino procura o ponto exato depois"


def test_sem_nenhuma_api_o_motor_local_usa_o_cep_vizinho():
    CoordenadaCep.objects.create(cep="21941590", latitude=Decimal("-22.86"),
                                 longitude=Decimal("-43.22"), fonte="awesomeapi")
    with _api():
        assert geo.coordenada("21941806") == (Decimal("-22.86"), Decimal("-43.22"))
    assert CoordenadaCep.objects.get(cep="21941806").fonte == "vizinho 21941590"


def test_cep_sem_fonte_e_sem_vizinho_usa_a_cidade_do_checkout_ou_explica():
    cidade = [{"lat": "-22.82", "lon": "-42.99", "address": {"city": "São Gonçalo"}}]
    with _api(nominatim=cidade):
        assert geo.coordenada("24400000", cidade="Sao Goncalo", uf="RJ") == (
            Decimal("-22.82"), Decimal("-42.99"))
    with _api(), pytest.raises(geo.GeoErro, match="nenhuma fonte"):
        geo.coordenada("69900000")


def test_rota_usa_o_segundo_servidor_quando_o_primeiro_cai():
    with _api(**{"routing.openstreetmap.de": {"routes": [{"distance": 432843.2}]}}):
        assert geo.distancia_km(SE, PIO_X) == (Decimal("432.8"), True)


def _rotas_aprendidas(fator):
    """5 destinos com rota real = linha reta x fator."""
    CoordenadaCep.objects.create(cep="01001000", latitude=SE[0], longitude=SE[1], fonte="t")
    for i in range(5):
        ponto = (SE[0] + Decimal(i + 1) / 10, SE[1])
        CoordenadaCep.objects.create(cep=f"0200000{i}", latitude=ponto[0], longitude=ponto[1],
                                     fonte="t")
        DistanciaCep.objects.create(origem="01001000", destino=f"0200000{i}",
                                    km=(geo.linha_reta_km(SE, ponto) * fator).quantize(
                                        Decimal("0.1")))


def test_sem_rota_estima_com_o_fator_aprendido_e_o_preco_nao_muda():
    """A estimativa fica guardada: a cotacao seguinte do mesmo checkout da o mesmo km."""
    _rotas_aprendidas(Decimal("1.5"))
    CoordenadaCep.objects.create(cep="20040020", latitude=PIO_X[0], longitude=PIO_X[1], fonte="t")
    with _api():
        km, exata = geo.km_entre_ceps("01001000", "20040020")
    reta = geo.linha_reta_km(SE, PIO_X)
    assert not exata and abs(km - reta * Decimal("1.5")) < 2
    with _api() as api:
        assert geo.km_entre_ceps("01001000", "20040020") == (km, False)
    assert api.call_count == 0


def test_refino_troca_a_estimativa_pela_rota_e_o_cep_aproximado_pelo_exato():
    from apps.logistica.tasks import refinar_cep, refinar_distancia

    CoordenadaCep.objects.create(cep="01001000", latitude=SE[0], longitude=SE[1], fonte="t")
    CoordenadaCep.objects.create(cep="20040020", latitude=Decimal("-22.9"),
                                 longitude=Decimal("-43.1"), fonte="vizinho", aproximada=True)
    DistanciaCep.objects.create(origem="01001000", destino="20040020", km=1, exata=False)
    with _api(awesomeapi={"lat": "-22.9004", "lng": "-43.178"}):
        refinar_cep("20040020")
    assert CoordenadaCep.objects.get(cep="20040020").aproximada is False
    assert not DistanciaCep.objects.exists(), "a distancia velha sai com o ponto velho"
    DistanciaCep.objects.create(origem="01001000", destino="20040020", km=1, exata=False)
    with _api(**{"project-osrm": {"routes": [{"distance": 432843.2}]}}):
        refinar_distancia("01001000", "20040020")
    assert DistanciaCep.objects.get().km == Decimal("432.8")


@pytest.mark.parametrize("erro", [ConnectionResetError("conexao cortada"),
                                  __import__("http.client").client.IncompleteRead(b"")])
def test_conexao_cortada_vira_geoerro_e_nao_erro_500(erro):
    """Erro de rede fora do URLError subia ate a view: 500 no checkout = backup rate."""
    with patch("urllib.request.urlopen", side_effect=erro), pytest.raises(geo.GeoErro):
        geo_rede._json("https://cep.awesomeapi.com.br/json/21941806", 1)


def test_sem_tempo_no_limite_nem_chama_a_api():
    """O tempo do checkout e um so: chamada que nao cabe nele falha na hora."""
    with patch("urllib.request.urlopen") as rede, geo.limite(0), \
            pytest.raises(geo.GeoErro, match="tempo"):
        geo_rede.buscar("https://cep.awesomeapi.com.br/json/21941806", 3)
    assert not rede.called


def test_retentativa_e_tempo_que_resta():
    """A primeira conexao a uma API fria falha: a segunda tentativa ainda cabe no limite."""
    respostas = [geo.GeoErro("timed out"), {"ok": True}]
    with patch.object(geo_rede, "_json", side_effect=respostas) as api, geo.limite(1.0):
        assert geo_rede.buscar("https://x", 5) == {"ok": True}
    assert all(0 < chamada.args[1] <= 1.0 for chamada in api.call_args_list)
