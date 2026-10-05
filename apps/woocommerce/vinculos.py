"""Vinculo id da loja WooCommerce <-> registro do hub (apps/integracoes/vinculos.py)."""

from apps.core.models import Origin
from apps.integracoes.vinculos import Vinculos

PLATAFORMA = Origin.WOOCOMMERCE
_vinculos = Vinculos(PLATAFORMA)
objeto_id = _vinculos.objeto_id
existente = _vinculos.existente
referenciar = _vinculos.referenciar
externo_id = _vinculos.externo_id
