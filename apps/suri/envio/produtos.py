"""Produto, estoque e pedido do hub -> Suri Shop.

- produto: POST shop/products (cria com o id "sh-<pk>"), PUT shop/products (o objeto
  inteiro), DELETE shop/products/<id>. Cada SKU ganha o vinculo "variantes".
- estoque: PUT shop/products/<id>/stocks so do SKU que mudou, na loja do estoque.
- pedido: nasce no Suri. O hub manda o que o Suri ainda nao tem: pago, cancelado ou a
  logistica (entregue). O estado do Suri fica no metadata do vinculo do pedido.
"""

from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.loja.models import Pedido, Produto, VarianteProduto
from apps.loja.services.pedidos import transacao
from apps.suri import vinculos
from apps.suri.envio.base import RecursoSuri
from apps.suri.envio.produtos_corpo import corpo


class ProdutoSuri(RecursoSuri):
    recurso = entidade = "produtos"
    modelo = Produto

    def _corpo(self, produto):
        return corpo(self.marketplace.enviador("categorias"), produto, self.loja_do_estoque(),
                     self.configuracao)

    def _vincular_variantes(self, produto, dados):
        skus = {d["sku"] for d in dados["dimensions"]}
        for variante in produto.variantes.all():
            sku = variante.sku or f"{dados['id']}-{variante.pk}"
            if sku in skus:
                vinculos.referenciar("variantes", vinculos.id_variacao(dados["id"], sku),
                                     variante, pai=dados["id"])

    def criar(self, obj):
        dados = self._corpo(obj)
        self.cliente.post("shop/products", dados)
        self._vincular_variantes(obj, dados)
        return dados["id"]

    def atualizar(self, obj, external_id):
        dados = self._corpo(obj)
        self.cliente.put("shop/products", dados)
        self._vincular_variantes(obj, dados)

    def excluir(self, external_id):
        self.cliente.delete(f"shop/products/{external_id}")


class EstoqueSuri(RecursoSuri):
    recurso = "estoque"
    entidade = "variantes"  # o vinculo e "<produto>:<sku>", com o produto no pai
    modelo = VarianteProduto

    def criar(self, obj):
        raise EnvioNaoSuportado("estoque so vai para variante ja vinculada; envie o produto.")

    def excluir(self, external_id):
        raise EnvioNaoSuportado("estoque nao se exclui; sai junto com o produto.")

    def atualizar(self, obj, external_id):
        produto_id, _, sku = external_id.partition(":")
        self.cliente.put(f"shop/products/{produto_id}/stocks", {"skus": [
            {"sku": sku, "stocks": {self.loja_do_estoque():
                                    {"stock": max(obj.inventory_quantity, 0)}}}]})


ENTREGUE = 4
PAGOS = (Pedido.Status.PROCESSANDO, Pedido.Status.CONCLUIDO)


class PedidoSuri(RecursoSuri):
    recurso = entidade = "pedidos"
    modelo = Pedido

    def criar(self, obj):
        raise EnvioNaoSuportado("pedido nasce no Suri: o hub nao cria pedido la.")

    def excluir(self, external_id):
        raise EnvioNaoSuportado("pedido nao e excluido no Suri pelo hub.")

    def atualizar(self, obj, external_id):
        referencia = vinculos.referencia("pedidos", obj.pk)
        estado = dict(referencia.metadata or {}) if referencia else {}
        if obj.status == Pedido.Status.CANCELADO and not estado.get("cancelado"):
            self.cliente.post("shop/orders/cancel", {"orderId": external_id})
            estado["cancelado"] = True
        elif obj.status in PAGOS and not estado.get("pago") and not estado.get("cancelado"):
            self.cliente.post("shop/orders/paid", {"orderId": external_id,
                                                   "paymentTracking": transacao(obj)})
            estado["pago"] = True
        entregue = (obj.status == Pedido.Status.CONCLUIDO
                    or obj.fulfillment_status == Pedido.StatusEntrega.ATENDIDO)
        if entregue and estado.get("logistica") != ENTREGUE and not estado.get("cancelado"):
            self.cliente.post("shop/orders/logistic", {"id": external_id, "status": ENTREGUE})
            estado["logistica"] = ENTREGUE
        if referencia and estado != referencia.metadata:
            referencia.metadata = estado
            referencia.save(update_fields=["metadata", "updated_at"])
