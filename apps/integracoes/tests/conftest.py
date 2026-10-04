"""Fixtures do envio: marketplaces falsos no registro e fila do Celery capturada."""

import pytest

from apps.integracoes.envio import registro
from apps.integracoes.models import ConfiguracaoIntegracao

from .envio_falso import MarketplaceFalso, ShopifyFalso, chamadas


@pytest.fixture
def falsos():
    antes = dict(registro._classes)
    registro._classes.clear()
    registro.registrar(MarketplaceFalso)
    registro.registrar(ShopifyFalso)
    chamadas.clear()
    yield chamadas
    registro._classes.clear()
    registro._classes.update(antes)


@pytest.fixture
def enfileirados(monkeypatch):
    """Troca o .delay do Celery por uma lista: (plataforma, recurso, operacao, pk)."""
    lista = []

    def enfileirar(configuracao_id, recurso, operacao, pk):
        plataforma = ConfiguracaoIntegracao.all_objects.get(pk=configuracao_id).plataforma
        lista.append((plataforma, recurso, operacao, str(pk)))

    monkeypatch.setattr("apps.integracoes.envio.distribuidor._enfileirar", enfileirar)
    return lista

