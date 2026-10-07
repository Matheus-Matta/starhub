from django.db import models
from django.utils.text import slugify

from .base import ComDatas


def sku_do_servico(nome):
    """SKU que o servico ganha ao nascer sozinho: "Montagem" -> "SERV-MONTAGEM"."""
    return f"SERV-{slugify(nome).upper()}"[:100]


class Servico(ComDatas):
    """Servico extra vendido junto com o item (montagem, impermeabilizacao, garantia).

    Nao e Produto de proposito: produto do hub vai para as lojas como item a venda.
    O pedido guarda o nome, a opcao e o preco que o cliente pagou; daqui saem o id e o
    SKU que o ERP usa para reconhecer o servico (API Woo, meta "starhub" do item).
    """

    nome = models.CharField("nome", max_length=150)
    nome_normalizado = models.CharField(max_length=150, editable=False)
    sku = models.CharField(
        "SKU", max_length=100,
        help_text="Codigo do servico no ERP. Nasce como SERV-<NOME> quando o servico chega "
                  "num pedido sem cadastro; troque pelo codigo do ERP.",
    )

    class Meta:
        verbose_name = "servico"
        verbose_name_plural = "servicos"
        ordering = ["nome"]
        constraints = [
            # Dois pedidos chegando juntos com um servico novo: o banco segura o repetido.
            models.UniqueConstraint(fields=["account", "nome_normalizado"],
                                    name="servico_nome_conta_unico"),
            models.UniqueConstraint(fields=["account", "sku"], name="servico_sku_conta_unico"),
        ]

    def save(self, *args, **kwargs):
        self.nome = self.nome.strip()
        self.nome_normalizado = self.nome.casefold()
        self.sku = (self.sku or sku_do_servico(self.nome)).strip()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome
