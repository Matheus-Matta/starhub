"""CPF e CNPJ validos (digitos verificadores certos) e sempre os mesmos por semente."""


def _verificador(numeros, pesos):
    resto = sum(n * p for n, p in zip(numeros, pesos, strict=False)) % 11
    return 0 if resto < 2 else 11 - resto


def cpf(semente):
    numeros = [int(d) for d in f"{(semente * 7919 + 123456789) % 10**9:09d}"]
    if len(set(numeros)) == 1:  # 111.111.111-xx e parecidos sao recusados
        numeros[0] = (numeros[0] + 1) % 10
    for tamanho in (9, 10):
        soma = sum(n * (tamanho + 1 - i) for i, n in enumerate(numeros))
        numeros.append(soma * 10 % 11 % 10)
    return "".join(map(str, numeros))


def cnpj(semente):
    numeros = [int(d) for d in f"{(semente * 104729 + 11222333) % 10**8:08d}"] + [0, 0, 0, 1]
    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    numeros.append(_verificador(numeros, pesos))
    numeros.append(_verificador(numeros, [6, *pesos]))
    return "".join(map(str, numeros))
