"""Acumula eventos no cache e entrega ao worker em lotes sem perder a versao nova."""

import json
import threading
import uuid
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache
from redis import Redis

CHAVE_FILA = "starhub:integracoes:envios-pendentes"
CHAVE_TRAVA = "starhub:integracoes:envios-em-processamento"
LIMITE = 1000
SEGUNDOS_TRAVA = 35 * 60
OPERACOES = {"create", "update", "delete"}

_ACUMULAR = """
local anterior = redis.call('HGET', KEYS[1], ARGV[1])
local operacao = ARGV[2]
if anterior then
    local separador = string.find(anterior, '|', 1, true)
    local anterior_operacao = string.sub(anterior, 1, separador - 1)
    if anterior_operacao == 'create' and operacao ~= 'delete' then
        operacao = 'create'
    end
end
local valor = operacao .. '|' .. ARGV[3]
redis.call('HSET', KEYS[1], ARGV[1], valor)
return valor
"""

_INICIAR = """
local pegou = redis.call('SET', KEYS[2], ARGV[1], 'NX', 'EX', ARGV[2])
if not pegou then return {} end
local pagina = redis.call('HSCAN', KEYS[1], '0', 'COUNT', ARGV[3])
return pagina[2]
"""

_CONFIRMAR = """
if redis.call('GET', KEYS[2]) ~= ARGV[1] then return 0 end
if redis.call('HGET', KEYS[1], ARGV[2]) == ARGV[3] then
    redis.call('HDEL', KEYS[1], ARGV[2])
end
redis.call('EXPIRE', KEYS[2], ARGV[4])
return 1
"""

_FINALIZAR = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""

_local_guard = threading.RLock()
_local_token = None


@dataclass(frozen=True)
class Evento:
    configuracao_id: str
    recurso: str
    operacao: str
    pk: str
    versao: str
    campo: str
    valor: str


def _campo(configuracao_id, recurso, pk):
    return json.dumps([str(configuracao_id), str(recurso), str(pk)], separators=(",", ":"))


def _evento(campo, valor):
    configuracao_id, recurso, pk = json.loads(campo)
    operacao, versao = valor.split("|", 1)
    return Evento(configuracao_id, recurso, operacao, pk, versao, campo, valor)


def _combinar(anterior, operacao):
    anterior = anterior.split("|", 1)[0] if anterior else None
    return "create" if anterior == "create" and operacao != "delete" else operacao


def _chave(nome):
    prefixo = settings.CACHES["default"].get("KEY_PREFIX", "")
    return f"{prefixo}:{nome}" if prefixo else nome


@lru_cache(maxsize=1)
def _redis():
    configuracao = settings.CACHES["default"]
    if not configuracao["BACKEND"].endswith(".RedisCache"):
        return None
    local = configuracao["LOCATION"]
    if isinstance(local, (list, tuple)):
        local = local[0]
    return Redis.from_url(
        local, decode_responses=True, socket_connect_timeout=0.5,
        socket_timeout=1, retry_on_timeout=False, health_check_interval=30,
    )


def acumular(configuracao_id, recurso, operacao, pk):
    if operacao not in OPERACOES:
        raise ValueError(f"Operacao de envio invalida: {operacao}")
    campo, versao = _campo(configuracao_id, recurso, pk), uuid.uuid4().hex
    cliente = _redis()
    if cliente is not None:
        cliente.eval(_ACUMULAR, 1, _chave(CHAVE_FILA), campo, operacao, versao)
        return
    with _local_guard:
        fila = dict(cache.get(CHAVE_FILA, {}))
        operacao = _combinar(fila.get(campo), operacao)
        fila[campo] = f"{operacao}|{versao}"
        cache.set(CHAVE_FILA, fila, timeout=None)
    from apps.integracoes.envio import lote_dev

    lote_dev.agendar()


def iniciar(limite=LIMITE):
    global _local_token
    token = uuid.uuid4().hex
    cliente = _redis()
    if cliente is not None:
        plano = cliente.eval(
            _INICIAR, 2, _chave(CHAVE_FILA), _chave(CHAVE_TRAVA),
            token, SEGUNDOS_TRAVA, limite,
        )
        eventos = [_evento(plano[i], plano[i + 1]) for i in range(0, len(plano), 2)]
        if not eventos:
            finalizar(token)
            return None, []
        return token, eventos
    with _local_guard:
        if _local_token is not None:
            return None, []
        _local_token = token
        itens = list(cache.get(CHAVE_FILA, {}).items())[:limite]
        if not itens:
            _local_token = None
            return None, []
        return token, [_evento(*item) for item in itens]


def confirmar(token, evento):
    cliente = _redis()
    if cliente is not None:
        cliente.eval(
            _CONFIRMAR, 2, _chave(CHAVE_FILA), _chave(CHAVE_TRAVA),
            token, evento.campo, evento.valor, SEGUNDOS_TRAVA,
        )
        return
    with _local_guard:
        if token != _local_token:
            return
        fila = dict(cache.get(CHAVE_FILA, {}))
        if fila.get(evento.campo) == evento.valor:
            fila.pop(evento.campo)
            cache.set(CHAVE_FILA, fila, timeout=None)


def finalizar(token):
    global _local_token
    if not token:
        return
    cliente = _redis()
    if cliente is not None:
        cliente.eval(_FINALIZAR, 1, _chave(CHAVE_TRAVA), token)
        return
    with _local_guard:
        if token == _local_token:
            _local_token = None


def limpar():
    """Esvazia o armazenamento; usado para isolar os testes do acumulador."""
    global _local_token
    cliente = _redis()
    if cliente is not None:
        cliente.delete(_chave(CHAVE_FILA), _chave(CHAVE_TRAVA))
        return
    with _local_guard:
        cache.delete(CHAVE_FILA)
        _local_token = None


def ha_pendentes():
    cliente = _redis()
    if cliente is not None:
        return bool(cliente.hlen(_chave(CHAVE_FILA)))
    return bool(cache.get(CHAVE_FILA, {}))
