"""Confere a regra de no maximo 200 linhas por arquivo (roda no CI).

Uso:
    python scripts/check_tamanho_de_arquivo.py              # confere
    python scripts/check_tamanho_de_arquivo.py --atualizar  # grava a linha de base

A linha de base (scripts/tamanho_de_arquivo.baseline.json) guarda arquivos que
ja passavam do limite. Eles so reprovam se CRESCEREM. Arquivo novo acima do
limite sempre reprova: quebre por assunto.
"""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LIMITE = 200
EXTENSOES = {".py", ".html", ".css", ".js", ".svg"}
IGNORAR = {"example_templetes_react_to_convert_html", "migrations", "staticfiles", ".venv",
           "venv", "node_modules", "__pycache__", ".git"}
BASELINE = RAIZ / "scripts" / "tamanho_de_arquivo.baseline.json"


def arquivos():
    for caminho in RAIZ.rglob("*"):
        if caminho.suffix not in EXTENSOES or not caminho.is_file():
            continue
        if IGNORAR.intersection(caminho.relative_to(RAIZ).parts):
            continue
        yield caminho


def contar(caminho):
    with caminho.open(encoding="utf-8", errors="replace") as arquivo:
        return sum(1 for _ in arquivo)


def main():
    medidos = {c.relative_to(RAIZ).as_posix(): contar(c) for c in arquivos()}
    grandes = {nome: linhas for nome, linhas in medidos.items() if linhas > LIMITE}
    if "--atualizar" in sys.argv:
        BASELINE.write_text(json.dumps(grandes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Linha de base gravada com {len(grandes)} arquivo(s).")
        return 0
    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    falhas = [
        f"{nome}: {linhas} linhas (limite {LIMITE}"
        + (f", linha de base {base[nome]})" if nome in base else ")")
        for nome, linhas in sorted(grandes.items())
        if linhas > base.get(nome, LIMITE)
    ]
    for falha in falhas:
        print(falha)
    print(f"{len(medidos)} arquivo(s) conferido(s), {len(falhas)} acima do limite.")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
