"""Base dos enviadores do WooCommerce: o recurso e uma rota REST (products, customers...).

    criar     -> POST <rota>            (devolve o id do Woo, que vira o vinculo)
    atualizar -> PUT <rota>/<id>
    excluir   -> DELETE <rota>/<id>?force=true

O corpo e montado pela subclasse em `corpo(obj, criando)`.
"""

from apps.integracoes.envio.base import EnviadorRecurso
from apps.woocommerce.cliente import WooClient, WooErro


class RecursoWoo(EnviadorRecurso):
    rota = ""
    _cliente = None

    @property
    def cliente(self):
        # Um cliente por enviador: o produto variavel faz varias chamadas.
        if self._cliente is None:
            self._cliente = WooClient(self.configuracao)
        return self._cliente

    def corpo(self, obj, criando):
        raise NotImplementedError

    def depois(self, obj, resposta):
        """Gancho depois do POST/PUT (variacoes, vinculo das imagens)."""

    _erro_depois = None

    def enviar(self, operacao, pk):
        self._erro_depois = None
        resultado = super().enviar(operacao, pk)
        if self._erro_depois is not None:
            raise self._erro_depois
        return resultado

    def criar(self, obj):
        resposta = self.cliente.post(self.rota, self.corpo(obj, criando=True))
        # O create roda numa transacao da base: erro aqui desfaria o vinculo, e o
        # produto ja criado na loja seria criado de novo na proxima tentativa. O erro
        # do gancho sobe so depois do commit (enviar), com o vinculo gravado.
        try:
            self.depois(obj, resposta)
        except WooErro as erro:
            self._erro_depois = erro
        return resposta["id"]

    def atualizar(self, obj, external_id):
        resposta = self.cliente.put(f"{self.rota}/{external_id}", self.corpo(obj, criando=False))
        self.depois(obj, resposta)

    def excluir(self, external_id):
        try:
            self.cliente.delete(f"{self.rota}/{external_id}")
        except WooErro as erro:
            if erro.status != 404:  # ja apagado na loja: o objetivo foi cumprido
                raise
