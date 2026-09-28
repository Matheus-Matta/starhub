"""Leitura do arquivo .env (CHAVE=valor), sem dependencia externa.

    ler_env(BASE_DIR / ".env")  ->  {"USER_ADMIN": "admin", ...}

Linha vazia, comentario (#) e linha sem "=" sao ignoradas; aspas em volta do
valor saem. O .env nao e carregado no settings: so quem precisa le.
"""


def ler_env(caminho):
    valores = {}
    try:
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return valores
    for linha in linhas:
        linha = linha.strip().removeprefix("export ").strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = (parte.strip() for parte in linha.split("=", 1))
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        valores[chave] = valor
    return valores
