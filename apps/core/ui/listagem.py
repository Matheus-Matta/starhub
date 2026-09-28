"""Ajudas para o change_list do tema (botao "Filtros" com contador)."""


def filtros_ativos(changelist):
    """Quantos filtros da gaveta estao em uso. Conta filtro, nao parametro:
    o de periodo usa dois parametros (de/ate) e conta como um so."""
    total = 0
    for spec in getattr(changelist, "filter_specs", []):
        if hasattr(spec, "used_parameters"):
            total += bool(spec.used_parameters)
        elif hasattr(spec, "value"):
            total += spec.value() is not None
    return total
