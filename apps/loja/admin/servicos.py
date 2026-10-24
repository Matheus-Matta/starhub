"""Servicos e as regras de a quais produtos cada um vale.

Na pagina do servico as regras aparecem numa lista (uma por linha, pela ordem);
"Adicionar regra" e "Editar" abrem o RegraServicoAdmin (servico_regra.py) num
modal, igual as variantes na pagina do produto (apps/core/admin_lista_modal.py).
"""

from django.contrib import admin
from django.template.loader import render_to_string

from apps.core.admin_base import TemaModelAdmin
from apps.core.admin_lista_modal import url_popup
from apps.integracoes.admin_servicos import ServicosShopifyMixin
from apps.loja.models import RegraServico, Servico
from apps.loja.services.servicos_regras import produtos_da_regra


@admin.register(Servico)
class ServicoAdmin(ServicosShopifyMixin, TemaModelAdmin):
    # Servico nasce sozinho no pedido (SKU SERV-<NOME>); aqui o operador troca o SKU
    # pelo codigo do ERP, define o preco e as regras. O id e o do hub e nao muda.
    list_display = ["nome", "sku", "preco", "active", "updated_at"]
    search_fields = ["nome", "sku"]
    list_filter = ["active"]
    readonly_fields = ["lista_regras"]
    readonly_largos = ["lista_regras"]
    fieldsets = [
        ("Servico", {"fields": [("nome", "sku"), ("preco", "active")]}),
        ("Regras", {"classes": ["secao-lista"], "fields": ["lista_regras"],
                    "description": "Para cada produto vale a primeira regra que casa, pela "
                                   "ordem: e ela que da o preco."}),
    ]

    @admin.display(description="Regras")
    def lista_regras(self, obj):
        return lista_regras(obj)


def _criterios(regra):
    if regra.tipo == RegraServico.Tipo.PRODUTO:
        return "Produtos escolhidos"
    partes = [c.nome for c in regra.categorias.all()]
    if regra.preco_de is not None or regra.preco_ate is not None:
        partes.append(faixa_texto(regra.preco_de, regra.preco_ate))
    return " · ".join(partes) or "-"


def faixa_texto(de, ate):
    from apps.core.ui.formatos import moeda

    if de is not None and ate is not None:
        return f"{moeda(de)} a {moeda(ate)}"
    return f"a partir de {moeda(de)}" if de is not None else f"ate {moeda(ate)}"


def lista_regras(servico):
    """HTML da secao "Regras": uma linha por regra; o form abre no modal."""
    salvo = servico.pk is not None
    regras = list(servico.regras.prefetch_related("categorias")) if salvo else []
    linhas = [{
        "regra": regra,
        "criterios": _criterios(regra),
        "produtos": produtos_da_regra(regra).count(),
        "url_editar": url_popup("admin:loja_regraservico_change", regra.pk),
        "url_excluir": url_popup("admin:loja_regraservico_delete", regra.pk),
    } for regra in regras]
    return render_to_string("admin/loja/lista_regras_servico.html", {
        "linhas": linhas,
        "servico": servico,
        "url_adicionar": url_popup("admin:loja_regraservico_add", servico=servico.pk,
                                   account=servico.account_id) if salvo else None,
    })
