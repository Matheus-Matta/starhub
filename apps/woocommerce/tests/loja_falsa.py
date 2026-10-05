"""Loja WooCommerce em memoria no lugar do WooClient: teste nunca fala com loja real.

    loja = LojaFalsa({"products": [produto], "orders": [pedido]})
    loja.instalar(monkeypatch)   # todo modulo que cria WooClient passa a usar esta
"""

import itertools

from apps.integracoes import permissoes
from apps.integracoes.models import ConfiguracaoIntegracao

MODULOS = ("apps.woocommerce.sincronizar", "apps.woocommerce.sincronizar_produtos",
           "apps.woocommerce.webhooks", "apps.woocommerce.webhooks_cadastro",
           "apps.woocommerce.envio.base", "apps.woocommerce.frete_envio")


class LojaFalsa:
    def __init__(self, colecoes=None):
        self.colecoes = {rota: list(itens) for rota, itens in (colecoes or {}).items()}
        self.chamadas = []
        self._ids = itertools.count(900)

    def instalar(self, monkeypatch):
        for modulo in MODULOS:
            monkeypatch.setattr(f"{modulo}.WooClient", lambda *_a, **_k: self)
        return self

    def listar(self, caminho, **params):
        self.chamadas.append(("LISTAR", caminho, params))
        return iter(self.colecoes.get(caminho, []))

    def contar(self, caminho, **params):
        return len(self.colecoes.get(caminho, []))

    def get(self, caminho, **params):
        self.chamadas.append(("GET", caminho, params))
        rota, _, item_id = caminho.rpartition("/")
        if caminho in self.colecoes or not item_id.isdigit():  # rota de lista
            return self.colecoes.get(caminho, [])
        return next(i for i in self.colecoes.get(rota, []) if str(i["id"]) == item_id)

    def post(self, caminho, corpo):
        self.chamadas.append(("POST", caminho, corpo))
        if caminho.endswith("/batch"):
            return {"create": [{"id": next(self._ids), **c} for c in corpo.get("create", [])],
                    "update": corpo.get("update", [])}
        resposta = {"id": next(self._ids), **corpo}
        resposta["images"] = [{"id": next(self._ids), **i} for i in corpo.get("images", [])]
        return resposta

    def put(self, caminho, corpo):
        self.chamadas.append(("PUT", caminho, corpo))
        if isinstance(corpo, list):  # ex.: locais da zona de entrega
            return corpo
        item_id = caminho.rpartition("/")[2]
        return {"id": int(item_id) if item_id.isdigit() else item_id, **corpo,
                "images": [i if "id" in i else {"id": next(self._ids), **i}
                           for i in corpo.get("images", [])]}

    def delete(self, caminho):
        self.chamadas.append(("DELETE", caminho, None))
        return {}


def configuracao(conta, receber=(), enviar=(), **campos):
    """Configuracao WooCommerce com as operacoes ligadas: ("produtos", "get"), ..."""
    matriz = permissoes.matriz_vazia()
    for direcao, ligados in (("receber", receber), ("enviar", enviar)):
        for recurso, operacao in ligados:
            matriz[direcao][recurso][operacao] = True
    cfg = ConfiguracaoIntegracao(
        account=conta, plataforma=ConfiguracaoIntegracao.Plataforma.WOOCOMMERCE,
        nome="Principal", dominio_loja="https://loja.test", permissoes=matriz,
        url_webhook="https://hub.test/integracoes/woocommerce/webhook", **campos)
    cfg.token_acesso, cfg.segredo_app = "ck_teste", "cs_teste"
    cfg.save()
    return cfg
