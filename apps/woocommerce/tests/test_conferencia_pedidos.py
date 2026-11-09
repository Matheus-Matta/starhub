"""Conferencia do beat na loja WooCommerce: so os pedidos alterados na janela."""

import pytest

from apps.integracoes.models import ExecucaoIntegracao
from apps.loja.models import Pedido
from apps.woocommerce.tasks import sincronizar_woocommerce
from apps.woocommerce.tests import exemplos
from apps.woocommerce.tests.loja_falsa import LojaFalsa, configuracao

pytestmark = pytest.mark.django_db
JANELA = {"inicio": "2026-11-09T11:00:00+00:00", "fim": "2026-11-09T12:05:00+00:00",
          "conferido_ate": "2026-11-09T12:00:00+00:00"}


def test_conferencia_pede_a_loja_so_os_pedidos_alterados_na_janela(conta, monkeypatch):
    """Sem o filtro a loja devolvia todos os pedidos dela a cada 30 minutos."""
    loja = LojaFalsa({"orders": [exemplos.pedido()],
                      "products": [exemplos.produto_simples()]}).instalar(monkeypatch)
    cfg = configuracao(conta, receber=(("pedidos", "get"),))
    execucao = ExecucaoIntegracao.all_objects.create(
        account_id=conta.pk, configuracao=cfg, tipo=ExecucaoIntegracao.Tipo.SINCRONIZAR,
        parametros={"direcao": "importar", "recursos": ["pedidos"], "janela": JANELA})

    sincronizar_woocommerce(str(execucao.pk))

    # Criado ou alterado: o modified cobre os dois (pedido novo tambem e "alterado").
    assert ("LISTAR", "orders", {"modified_after": "2026-11-09T11:00:00",
                                 "modified_before": "2026-11-09T12:05:00",
                                 "dates_are_gmt": "true"}) in loja.chamadas
    assert Pedido.objects.count() == 1
