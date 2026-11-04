class NumeroInvalido(ValueError):
    pass


def numero_whatsapp(valor):
    """Numero so com digitos e DDI; celular brasileiro pode chegar sem o 55."""
    digitos = "".join(caractere for caractere in str(valor or "") if caractere.isdigit())
    if len(digitos) in {10, 11}:
        digitos = f"55{digitos}"
    if not 10 <= len(digitos) <= 15:
        raise NumeroInvalido("Informe um telefone com DDD e, se necessario, o codigo do pais.")
    return digitos
