"""Campos, secoes e inlines que so aparecem conforme o valor de outro campo.

No ModelAdmin (ou no inline, com campos da mesma linha):

    condicoes = {
        "url_externa": {"campo": "tipo", "em": ["external"]},       # select/texto
        "#componentes-group": {"campo": "tipo", "em": ["bundle"]},  # inline inteiro
        "inventory_quantity": {"campo": "manage_inventory", "marcado": True},  # switch
        "sale_starts_at": {"campo": "sale_price", "preenchido": True},
        "tags": [regra_a, regra_b],                                  # lista = basta uma
    }

A chave e o nome de um campo ou um seletor CSS ("#id", ".classe") para inline e
secao. Quem mostra e esconde e static/starhub/js/condicoes.js; o servidor nao
muda nada no que e salvo (campo escondido continua indo no POST). Campo com
erro nunca fica escondido: o usuario precisa ver o que corrigir.
"""

from django.core.exceptions import ImproperlyConfigured

TESTES = {"em", "marcado", "preenchido"}


def regras(regra):
    return regra if isinstance(regra, list) else [regra]


def validar(condicoes, dono):
    """Erro de digitacao na regra estoura ao abrir a tela, e nao some em silencio no JS."""
    for alvo, regra in condicoes.items():
        for item in regras(regra):
            if "campo" not in item or len(TESTES.intersection(item)) != 1:
                raise ImproperlyConfigured(
                    f"{dono}.condicoes[{alvo!r}]: use 'campo' e um de {sorted(TESTES)}."
                )
    return condicoes


def para_tela(model_admin, inline_admin_formsets):
    """JSON que o change_form entrega ao condicoes.js (None quando nao ha regra)."""
    dados = {"form": validar(model_admin.condicoes, type(model_admin).__name__), "inlines": {}}
    for inline in inline_admin_formsets:
        condicoes = getattr(inline.opts, "condicoes", {})
        if condicoes:
            dados["inlines"][inline.formset.prefix] = validar(condicoes, type(inline.opts).__name__)
    return dados if dados["form"] or dados["inlines"] else None
