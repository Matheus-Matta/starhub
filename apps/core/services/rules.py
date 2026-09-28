from django.core.exceptions import ValidationError

OPERATORS = {
    "eq", "neq", "gt", "gte", "lt", "lte", "contains", "not_contains",
    "in", "not_in", "is_null", "is_not_null",
}


def validate_rules(rules):
    if not isinstance(rules, dict) or set(rules) - {"all", "any"}:
        raise ValidationError("Rules deve conter apenas 'all' e/ou 'any'.")
    for group, conditions in rules.items():
        if not isinstance(conditions, list):
            raise ValidationError(f"{group} deve ser uma lista.")
        for condition in conditions:
            if not isinstance(condition, dict):
                raise ValidationError("Cada regra deve ser um objeto.")
            if set(condition) - {"field", "operator", "value"}:
                raise ValidationError("A regra possui chaves nao permitidas.")
            if not condition.get("field") or condition.get("operator") not in OPERATORS:
                raise ValidationError("Campo ou operador de regra invalido.")


def _resolve(data, path):
    value = data
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else getattr(value, part, None)
    return value


def _evaluate(value, operator, expected):
    operations = {
        "eq": lambda: value == expected,
        "neq": lambda: value != expected,
        "gt": lambda: value is not None and value > expected,
        "gte": lambda: value is not None and value >= expected,
        "lt": lambda: value is not None and value < expected,
        "lte": lambda: value is not None and value <= expected,
        "contains": lambda: expected in value if value is not None else False,
        "not_contains": lambda: expected not in value if value is not None else True,
        "in": lambda: value in expected,
        "not_in": lambda: value not in expected,
        "is_null": lambda: value is None,
        "is_not_null": lambda: value is not None,
    }
    return operations[operator]()


def matches_rules(subject, rules):
    validate_rules(rules)
    results = {}
    for group, conditions in rules.items():
        values = [
            _evaluate(_resolve(subject, item["field"]), item["operator"], item.get("value"))
            for item in conditions
        ]
        results[group] = all(values) if group == "all" else any(values)
    return all(results.values())
