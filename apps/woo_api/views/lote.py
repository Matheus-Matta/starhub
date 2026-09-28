"""POST /<recurso>/batch: {"create": [...], "update": [...], "delete": [ids]}.

Cada operacao roda na sua propria transacao, como no Woo: um item com erro
volta com {"id", "error"} e nao desfaz os outros.
"""

from rest_framework.response import Response

from apps.woo_api.erros import WooErro, parametro_invalido
from apps.woo_api.views.base import WooView, excluir, gravar

LIMITE_LOTE = 100


def _erro(id_, erro):
    return {"id": id_, "error": erro.como_dict()}


class LoteView(WooView):
    def post(self, request):
        corpo = self.corpo()
        operacoes = {chave: corpo.get(chave) or [] for chave in ("create", "update", "delete")}
        for chave, lista in operacoes.items():
            if not isinstance(lista, list):
                raise parametro_invalido(chave, f"{chave} nao e do tipo array.")
        if sum(len(lista) for lista in operacoes.values()) > LIMITE_LOTE:
            raise WooErro(
                "woocommerce_rest_request_entity_too_large",
                f"Limite de {LIMITE_LOTE} objetos por lote. Divida em lotes menores.",
                413,
            )
        recurso = self.recurso()
        resposta = {}
        if "create" in corpo:
            resposta["create"] = [self._criar(recurso, dados) for dados in operacoes["create"]]
        if "update" in corpo:
            resposta["update"] = [self._alterar(recurso, dados) for dados in operacoes["update"]]
        if "delete" in corpo:
            resposta["delete"] = [self._excluir(recurso, pk) for pk in operacoes["delete"]]
        return Response(resposta)

    put = post
    patch = post

    def _criar(self, recurso, dados):
        try:
            if not isinstance(dados, dict):
                raise WooErro("rest_invalid_json", "Cada item precisa ser um objeto.", 400)
            return recurso.para_woo(gravar(recurso, recurso.modelo(), dados, criando=True))
        except WooErro as erro:
            return _erro(0, erro)

    def _alterar(self, recurso, dados):
        id_ = dados.get("id", 0) if isinstance(dados, dict) else 0
        try:
            recurso.obter(id_)
            return recurso.para_woo(gravar(recurso, id_, dados, criando=False))
        except WooErro as erro:
            return _erro(id_, erro)

    def _excluir(self, recurso, pk):
        try:
            # No lote o Woo exclui de vez (force=true).
            return excluir(recurso, pk, forcar=True)
        except WooErro as erro:
            return _erro(pk, erro)
