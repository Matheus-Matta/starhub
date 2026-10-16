from decimal import Decimal, InvalidOperation

from apps.starchats.contexto import resolver


def _esperado(texto, atual):
    valor = (texto or "").strip()
    if isinstance(atual, bool):
        return valor.casefold() in {"1", "true", "sim", "yes"}
    if isinstance(atual, Decimal):
        try:
            return Decimal(valor.replace(",", "."))
        except InvalidOperation:
            return valor
    return valor


def avaliar(regra, contexto):
    atual = resolver(contexto, regra.campo)
    operador = regra.operador
    if operador == "is_null":
        return atual in (None, "")
    if operador == "is_not_null":
        return atual not in (None, "")
    esperado = _esperado(regra.valor, atual)
    if operador in {"contains", "not_contains"}:
        contem = str(esperado).casefold() in str(atual or "").casefold()
        return contem if operador == "contains" else not contem
    if operador == "eq":
        return atual == esperado
    if operador == "neq":
        return atual != esperado
    if atual is None:
        return False
    operacoes = {
        "gt": lambda: atual > esperado,
        "gte": lambda: atual >= esperado,
        "lt": lambda: atual < esperado,
        "lte": lambda: atual <= esperado,
    }
    try:
        return operacoes[operador]()
    except (KeyError, TypeError):
        return False


def conjunto_atende(conjunto, contexto):
    resultados = [avaliar(regra, contexto) for regra in conjunto.regras.all()]
    if not resultados:
        return True
    return all(resultados) if conjunto.modo == "all" else any(resultados)
