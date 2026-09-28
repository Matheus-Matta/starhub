import secrets

from django.core.validators import MinValueValidator
from django.db import models

from .base import NAO_NEGATIVO, ComDatas, JSONDecimalField


def nova_chave_pedido():
    return f"wc_order_{secrets.token_hex(7)[:13]}"


def novo_numero_pedido():
    return f"SH-{secrets.token_hex(5).upper()}"


def _dinheiro(rotulo):
    return models.DecimalField(
        rotulo, max_digits=12, decimal_places=2, default=0, validators=NAO_NEGATIVO
    )


class Pedido(ComDatas):
    class Status(models.TextChoices):
        RASCUNHO = "checkout-draft", "Rascunho"
        PENDENTE = "pending", "Pendente"
        CONFIRMADO = "confirmed", "Confirmado"
        PROCESSANDO = "processing", "Processando"
        AGUARDANDO = "on-hold", "Aguardando"
        CONCLUIDO = "completed", "Concluido"
        CANCELADO = "cancelled", "Cancelado"
        REEMBOLSADO = "refunded", "Reembolsado"
        FALHOU = "failed", "Falhou"
        ARQUIVADO = "archived", "Arquivado"
        LIXEIRA = "trash", "Lixeira"

    class StatusFinanceiro(models.TextChoices):
        PENDENTE = "pending", "Pendente"
        AUTORIZADO = "authorized", "Autorizado"
        PAGO = "paid", "Pago"
        PARCIAL = "partially_paid", "Parcialmente pago"
        REEMBOLSADO = "refunded", "Reembolsado"
        REEMBOLSO_PARCIAL = "partially_refunded", "Reembolso parcial"
        ESTORNADO = "voided", "Estornado"
        FALHOU = "failed", "Falhou"

    class StatusEntrega(models.TextChoices):
        NAO_ATENDIDO = "unfulfilled", "Nao atendido"
        PARCIAL = "partial", "Parcial"
        ATENDIDO = "fulfilled", "Atendido"
        DEVOLVIDO = "returned", "Devolvido"

    PAGOS = (Status.PROCESSANDO, Status.CONCLUIDO)

    number = models.CharField("numero", max_length=30, default=novo_numero_pedido)
    external_number = models.CharField("numero externo", max_length=100, blank=True)
    status = models.CharField(
        "status", max_length=20, choices=Status, default=Status.PENDENTE, db_index=True
    )
    financial_status = models.CharField("situacao do pagamento",
        max_length=30, choices=StatusFinanceiro, default=StatusFinanceiro.PENDENTE
    )
    fulfillment_status = models.CharField("situacao da entrega",
        max_length=20, choices=StatusEntrega, default=StatusEntrega.NAO_ATENDIDO
    )
    moeda = models.CharField("moeda", max_length=3, default="BRL")
    subtotal = _dinheiro("subtotal")
    total_desconto = _dinheiro("total de desconto")
    total_frete = _dinheiro("total de frete")
    total_impostos = _dinheiro("total de impostos")
    total = _dinheiro("total")
    total_reembolsado = _dinheiro("total reembolsado")
    imposto_desconto = _dinheiro("imposto do desconto")
    imposto_frete = _dinheiro("imposto do frete")
    imposto_carrinho = _dinheiro("imposto dos itens")
    cliente = models.ForeignKey(
        "loja.Cliente", verbose_name="cliente", null=True, blank=True, on_delete=models.PROTECT,
        related_name="pedidos"
    )
    email = models.EmailField("e-mail", blank=True)
    telefone = models.CharField("telefone", max_length=30, blank=True)
    notas = models.TextField("notas", blank=True)
    observacao_cliente = models.TextField("observacao do cliente", blank=True)
    endereco_entrega = models.ForeignKey(
        "core.Address", verbose_name="endereco de entrega", null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="pedidos_entrega",
    )
    endereco_cobranca = models.ForeignKey(
        "core.Address", verbose_name="endereco de cobranca", null=True, blank=True,
        on_delete=models.PROTECT,
        related_name="pedidos_cobranca",
    )
    placed_at = models.DateTimeField("data do pedido", null=True, blank=True)
    paid_at = models.DateTimeField("pago em", null=True, blank=True)
    cancelled_at = models.DateTimeField("cancelado em", null=True, blank=True)
    fulfilled_at = models.DateTimeField("concluido em", null=True, blank=True)
    forma_pagamento = models.CharField("forma de pagamento", max_length=100, blank=True)
    forma_pagamento_titulo = models.CharField(
        "nome da forma de pagamento", max_length=200, blank=True
    )
    shipping_method = models.CharField("metodo de envio", max_length=150, blank=True)
    source_name = models.CharField("canal de origem", max_length=50, blank=True)
    source_reference = models.CharField("referencia na origem", max_length=255, blank=True)
    id_pai = models.PositiveBigIntegerField("pedido pai (id)", default=0)
    versao = models.CharField("versao", max_length=20, default="9.0.0")
    chave = models.CharField(
        "chave do pedido", max_length=40, unique=True, default=nova_chave_pedido
    )
    preco_inclui_imposto = models.BooleanField("preco inclui imposto", default=False)
    ip_cliente = models.CharField("IP do cliente", max_length=64, blank=True)
    user_agent = models.CharField("navegador do cliente", max_length=255, blank=True)
    hash_carrinho = models.CharField("hash do carrinho", max_length=64, blank=True)
    linhas_frete = JSONDecimalField("fretes", default=list, blank=True)
    linhas_imposto = JSONDecimalField("impostos", default=list, blank=True)
    linhas_taxa = JSONDecimalField("taxas", default=list, blank=True)
    linhas_cupom = JSONDecimalField("cupons aplicados", default=list, blank=True)
    reembolsos = JSONDecimalField("reembolsos", default=list, blank=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(
            fields=["account", "number"], name="pedido_numero_conta_unico"
        )]

    def __str__(self):
        return f"Pedido #{self.number}"


class ItemPedido(ComDatas):
    pedido = models.ForeignKey(
        Pedido, verbose_name="pedido", on_delete=models.CASCADE, related_name="itens"
    )
    produto = models.ForeignKey(
        "loja.Produto", verbose_name="produto", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="itens_pedido",
    )
    variante = models.ForeignKey(
        "loja.VarianteProduto", verbose_name="variante", null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="itens_pedido",
    )
    id_variacao = models.PositiveBigIntegerField("id da variacao", default=0)
    nome = models.CharField("nome", max_length=255, blank=True)
    sku = models.CharField("SKU", max_length=100, blank=True)
    quantidade = models.IntegerField(
        "quantidade", default=1, validators=[MinValueValidator(1)]
    )
    preco_unitario = _dinheiro("preco unitario")
    subtotal = _dinheiro("subtotal")
    total_desconto = _dinheiro("desconto")
    imposto_subtotal = _dinheiro("imposto do subtotal")
    imposto_total = _dinheiro("imposto total")
    total = _dinheiro("total")
    peso = models.DecimalField("peso", max_digits=12, decimal_places=3, null=True, blank=True)
    requer_entrega = models.BooleanField("requer entrega", default=True)
    classe_fiscal = models.CharField("classe fiscal", max_length=100, blank=True)
    impostos = JSONDecimalField("impostos", default=list, blank=True)

    class Meta:
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantidade} x {self.nome}"

    @property
    def preco(self):
        return self.total if not self.quantidade else self.total / self.quantidade

    def save(self, *args, **kwargs):
        if self.pedido_id and not self.account_id:
            self.account_id = self.pedido.account_id
        if self.variante_id:
            self.produto_id = self.produto_id or self.variante.produto_id
            self.sku = self.sku or self.variante.sku
            self.nome = self.nome or self.variante.produto.nome
            self.preco_unitario = self.preco_unitario or self.variante.current_price or 0
        super().save(*args, **kwargs)
