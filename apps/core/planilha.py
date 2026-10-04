"""Le uma planilha (.xlsx ou .csv) como lista de linhas {coluna: texto}.

O cabeçalho e a primeira linha e vale escrito de qualquer jeito: "E-mail", "email",
"Comentário" e "comentario" viram a mesma coluna (sem acento, minusculo, _ no lugar
de espaco e hifen). Linha toda vazia e pulada. O .csv aceita ; ou , (o Excel em
portugues salva com ;) e o UTF-8 com BOM que o Excel grava.
"""

import csv
import io
import unicodedata
from datetime import date, datetime

LINHAS_MAXIMO = 5000


class PlanilhaInvalida(ValueError):
    pass


def coluna(nome):
    sem_acento = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode()
    return "_".join(sem_acento.strip().lower().replace("-", " ").split())


def _texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))  # nota 5 do Excel chega como 5.0
    return str(valor).strip()


def _do_xlsx(conteudo):
    from openpyxl import load_workbook

    try:
        livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as erro:  # zip corrompido, nao e xlsx: a mensagem vai para o operador
        raise PlanilhaInvalida(f"Nao foi possivel abrir o .xlsx: {erro}") from erro
    try:
        return [[_texto(c) for c in linha] for linha in livro.active.iter_rows(values_only=True)]
    finally:
        livro.close()


def _do_csv(conteudo):
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("latin-1")  # CSV antigo do Excel no Windows
    amostra = texto[:4096]
    separador = ";" if amostra.count(";") > amostra.count(",") else ","
    return [[_texto(c) for c in linha] for linha in csv.reader(io.StringIO(texto),
                                                               delimiter=separador)]


def ler(conteudo, nome_arquivo):
    """[(numero da linha na planilha, {coluna: texto})], a partir da linha 2."""
    nome = nome_arquivo.lower()
    if nome.endswith(".xlsx"):
        linhas = _do_xlsx(conteudo)
    elif nome.endswith(".csv"):
        linhas = _do_csv(conteudo)
    else:
        raise PlanilhaInvalida("Envie a planilha em .xlsx ou .csv.")
    if not linhas:
        raise PlanilhaInvalida("A planilha esta vazia: falta o cabecalho na primeira linha.")
    cabecalho = [coluna(c) for c in linhas[0]]
    saida = []
    for numero, valores in enumerate(linhas[1:], start=2):
        if not any(valores):
            continue
        saida.append((numero, {k: v for k, v in zip(cabecalho, valores, strict=False) if k}))
    if len(saida) > LINHAS_MAXIMO:
        raise PlanilhaInvalida(
            f"A planilha tem {len(saida)} linhas; o maximo e {LINHAS_MAXIMO}. Divida em partes."
        )
    return saida
