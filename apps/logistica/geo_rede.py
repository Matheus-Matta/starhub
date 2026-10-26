"""Rede das APIs de CEP e rota: limite de tempo unico, retentativa e chamadas em paralelo.

    with limite(7):                       # o checkout tem um tempo so para tudo
        primeiro([lambda t: fonte_a(t), lambda t: fonte_b(t)], teto=3)

Cada chamada recebe o menor entre o seu teto e o que resta do limite; sem tempo, nem
abre a conexao. Em paralelo vale a primeira resposta util: uma API lenta nao segura as
outras. Erro de rede de qualquer tipo vira GeoErro, nunca uma excecao que derruba a view
(no checkout da Shopify, 500 = backup rate).
"""

import json
import logging
import time
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from contextvars import ContextVar
from http.client import HTTPException

logger = logging.getLogger(__name__)
# Abaixo disto nem vale abrir a conexao: a resposta nao chegaria a tempo.
MINIMO_SEGUNDOS = 0.2
# Uma retentativa por fonte: a falha comum e a primeira conexao lenta (API "fria").
TENTATIVAS = 2
AGENTE = "StarHub/1.0 (frete; contato stardev.sistemas)"
_limite = ContextVar("geo_limite", default=None)


class GeoErro(Exception):
    """CEP sem coordenada ou API fora: a mensagem vai para quem cotou."""


@contextmanager
def limite(segundos):
    """Tempo total para todas as chamadas dentro do bloco."""
    token = _limite.set(time.monotonic() + segundos)
    try:
        yield
    finally:
        _limite.reset(token)


def tempo(teto):
    """Segundos que esta chamada pode usar; GeoErro se o limite ja acabou."""
    fim = _limite.get()
    if fim is None:
        return teto
    resta = fim - time.monotonic()
    if resta < MINIMO_SEGUNDOS:
        raise GeoErro("sem tempo no limite do checkout para consultar a API")
    return min(teto, resta)


def _json(url, timeout):
    requisicao = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            return json.loads(resposta.read().decode())
    # OSError cobre URLError, timeout e a conexao cortada no meio da leitura; antes esta
    # ultima subia ate a view e virava 500 no checkout (backup rate na Shopify).
    except (OSError, HTTPException, ValueError) as erro:
        raise GeoErro(str(erro)) from erro


def buscar(url, teto):
    """JSON da URL com uma retentativa, tudo dentro do limite."""
    ultimo = None
    for _ in range(TENTATIVAS):
        try:
            return _json(url, tempo(teto))
        except GeoErro as erro:
            ultimo = erro
            if "sem tempo" in str(erro):
                break
    raise ultimo


def primeiro(chamadas, teto):
    """Roda as chamadas em paralelo e devolve a primeira resposta que nao e None.

    Cada chamada recebe o tempo em segundos. As que ficarem para tras terminam sozinhas
    (o socket tem timeout); o resultado delas e descartado.
    """
    if not chamadas:
        return None
    janela = tempo(teto)
    executor = ThreadPoolExecutor(max_workers=len(chamadas))
    pendentes = {executor.submit(chamada, janela) for chamada in chamadas}
    fim = time.monotonic() + janela
    try:
        while pendentes:
            prontas, pendentes = wait(pendentes, timeout=max(fim - time.monotonic(), 0),
                                      return_when=FIRST_COMPLETED)
            if not prontas:
                return None  # acabou o tempo
            for pronta in prontas:
                try:
                    resultado = pronta.result()
                # KeyError e cia.: resposta num formato inesperado vale como "nao achou".
                except (GeoErro, KeyError, IndexError, TypeError, ValueError) as erro:
                    logger.info("Fonte de CEP/rota falhou: %s", erro)
                    continue
                if resultado is not None:
                    return resultado
        return None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
