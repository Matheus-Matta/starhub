"""Produto, estoque e pedido do hub -> Suri Shop.

- produto: POST shop/products (cria com o id "sh-<pk>"), PUT shop/products (o objeto
  inteiro), DELETE shop/products/<id>. Cada SKU ganha o vinculo "variantes"; o servico
  que vai como variante, o vinculo "servicos" (apps/suri/servicos.py).
- estoque: PUT shop/products/<id>/stocks do SKU que mudou, na loja do estoque, das
  combinacoes dele com servico e dos kits que levam a variante (o maior estoque das pecas).
- pedido: nasce no Suri. O hub manda o que o Suri ainda nao tem: pago, cancelado ou a
  logistica (entregue). O estado do Suri fica no metadata do vinculo do pedido.
"""

from apps.integracoes.envio.base import EnvioNaoSuportado
from apps.loja.models import Pedido, Produto, VarianteProduto
from apps.loja.services.pedidos import transacao
from apps.suri import servicos as servicos_suri
from apps.suri import servicos_dimensoes, vinculos
from apps.suri.envio.base import RecursoSuri
from apps.suri.envio.produtos_corpo import corpo


class ProdutoSuri(RecursoSuri):
    recurso = entidade = "produtos"
    modelo = Produto

    def _corpo(self, produto):
        self._servicos = {}
        return corpo(self.marketplace.enviador("categorias"), produto, self.loja_do_estoque(),
                     self.configuracao, servicos_suri.do_produto(self.configuracao, produto),
                     self._servicos)

    def _vincular_variantes(self, produto, dados):
        servicos_suri.vincular(dados["id"], self._servicos)
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
        servicos_suri.desvincular(external_id)


class EstoqueSuri(RecursoSuri):
    recurso = "estoque"
    entidade = "variantes"  # o vinculo e "<produto>:<sku>", com o produto no pai
    modelo = VarianteProduto

    def criar(self, obj):
        raise EnvioNaoSuportado("estoque so vai para variante ja vinculada; envie o produto.")

    def excluir(self, external_id):
        raise EnvioNaoSuportado("estoque nao se exclui; sai junto com o produto.")

    def enviar(self, operacao, pk):
        # Antes da variante: o item do kit pode nem estar no Suri (o envio dela para
        # em "sem vinculo"), mas o servico do kit esta e precisa do numero novo.
        if operacao != "delete":
            self._servicos_dos_kits(pk)
        return super().enviar(operacao, pk)

    def _put(self, produto_id, quantidades):
        loja = self.loja_do_estoque()
        self.cliente.put(f"shop/products/{produto_id}/stocks", {"skus": [
            {"sku": sku, "stocks": {loja: {"stock": max(quantidade, 0)}}}
            for sku, quantidade in quantidades]})

    def _servicos_dos_kits(self, pk):
        kits = Produto.all_objects.filter(
            account_id=self.configuracao.account_id, tipo=Produto.Tipo.BUNDLE,
            componentes__component_variant_id=pk).distinct()
        for kit in kits:
            kit_id = vinculos.externo_id("produtos", kit.pk)
            skus = servicos_suri.skus_dos_servicos(kit_id) if kit_id else []
            if skus:
                quantidade = servicos_dimensoes.estoque(kit)
                self._put(kit_id, [(sku, quantidade) for sku in skus])

    def atualizar(self, obj, external_id):
        produto_id, _, sku = external_id.partition(":")
        if obj.produto.tipo == Produto.Tipo.BUNDLE:
            # O kit vende as pecas: as combinacoes ficam com o maior estoque delas.
            servicos = servicos_suri.skus_dos_servicos(produto_id)
            quantidade = servicos_dimensoes.estoque(obj.produto) if servicos else 0
        else:
            # Cada combinacao vende uma cor: so as dela mudam com a baixa dela.
            servicos = servicos_suri.skus_da_variante(produto_id, sku)
            quantidade = obj.inventory_quantity
        self._put(produto_id, [(sku, obj.inventory_quantity),
                               *((s, quantidade) for s in servicos)])


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
