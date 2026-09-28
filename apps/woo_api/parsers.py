import json
from decimal import Decimal

from django.conf import settings
from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


class JSONDecimalParser(JSONParser):
    """JSON com numero decimal virando Decimal, nunca float.

    O ERP pode mandar "regular_price": 19.9 (numero, sem aspas). O parser padrao
    transformaria em float e o centavo ja chegaria torto no banco.
    """

    def parse(self, stream, media_type=None, parser_context=None):
        codificacao = (parser_context or {}).get("encoding", settings.DEFAULT_CHARSET)
        try:
            texto = stream.read().decode(codificacao)
            return json.loads(texto, parse_float=Decimal) if texto.strip() else {}
        except (ValueError, UnicodeDecodeError) as erro:
            raise ParseError(f"JSON invalido: {erro}") from erro


class JSONQualquerTipo(JSONDecimalParser):
    """Ultimo da lista: le como JSON o corpo com Content-Type que nenhum outro
    parser aceitou (ex.: text/plain). ERP antigo manda o JSON do login assim,
    e sem isso a resposta seria 415 e o ERP so mostraria "erro ao autenticar"."""

    media_type = "*/*"
