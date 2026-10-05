"""Vinculo id do Suri Shop <-> registro do hub (apps/integracoes/vinculos.py).

Variacao do Suri nao tem id proprio, so o SKU dentro do produto: o vinculo
"variantes" usa "<id do produto>:<sku>" (`id_variacao`).
"""

from apps.core.models import Origin
from apps.integracoes.vinculos import Vinculos

PLATAFORMA = Origin.SURI
_vinculos = Vinculos(PLATAFORMA)
objeto_id = _vinculos.objeto_id
existente = _vinculos.existente
referenciar = _vinculos.referenciar
externo_id = _vinculos.externo_id
referencia = _vinculos.referencia


def id_variacao(produto_id, sku):
    return f"{produto_id}:{sku}"
