RECURSOS = (
    ("produtos", "Produtos"),
    ("categorias", "Categorias"),
    ("clientes", "Clientes"),
    ("pedidos", "Pedidos"),
    ("cupons", "Cupons"),
    ("estoque", "Estoque"),
    ("avaliacoes", "Avaliacoes"),
)
DIRECOES = (("receber", "Receber"), ("enviar", "Enviar"))
OPERACOES = (
    ("get", "Buscar"),
    ("create", "Criar"),
    ("update", "Atualizar"),
    ("delete", "Excluir"),
)


def matriz_vazia():
    return {
        direcao: {
            recurso: {operacao: False for operacao, _ in OPERACOES}
            for recurso, _ in RECURSOS
        }
        for direcao, _ in DIRECOES
    }


def normalizar(matriz):
    saida = matriz_vazia()
    if not isinstance(matriz, dict):
        return saida
    for direcao, recursos in saida.items():
        recebidos = matriz.get(direcao, {})
        if not isinstance(recebidos, dict):
            continue
        for recurso, operacoes in recursos.items():
            valores = recebidos.get(recurso, {})
            if isinstance(valores, dict):
                saida[direcao][recurso] = {
                    operacao: bool(valores.get(operacao)) for operacao in operacoes
                }
    return saida
