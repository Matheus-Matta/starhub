"""Base dos enviadores do Suri Shop: cliente, loja de estoque e id dos registros do hub.

O Suri grava produto e categoria com o id que o hub manda. Registro que nasceu no
hub vai como "sh-<pk>" (nao colide com os ids do Suri); o que veio do Suri volta com
o id de la (o vinculo).
"""

from apps.integracoes.envio.base import EnviadorRecurso
from apps.suri import vinculos
from apps.suri.cliente import SuriClient, SuriErro


def id_no_suri(recurso, obj):
    return vinculos.externo_id(recurso, obj.pk) or f"sh-{obj.pk}"


class RecursoSuri(EnviadorRecurso):
    _cliente = None
    _loja = None

    @property
    def cliente(self):
        if self._cliente is None:
            self._cliente = SuriClient(self.configuracao)
        return self._cliente

    def loja_do_estoque(self):
        """Id da loja do Suri que recebe o estoque: a primeira de GET shop/stores.

        O hub tem um estoque so; com varias lojas no Suri, todo ele vai para a primeira.
        """
        if self._loja is None:
            lojas = self.cliente.get("shop/stores") or []
            if not lojas:
                raise SuriErro("O Suri nao tem loja cadastrada; crie uma no Portal do Suri "
                               "para receber o estoque.")
            self._loja = str(lojas[0]["id"])
        return self._loja
