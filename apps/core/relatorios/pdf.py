"""PDF do relatorio (reportlab): A4 deitado, cabecalho da tabela repetido por pagina.

As cores ficam aqui e nao no tokens.css: o PDF nao le CSS e sai sempre em papel
branco, igual no tema claro e no escuro.
"""

from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

CINZA_CABECALHO = colors.HexColor("#F1F1F4")
CINZA_LINHA = colors.HexColor("#DBDFE9")
MARGEM = 10 * mm


def _estilos():
    base = getSampleStyleSheet()
    celula = ParagraphStyle("celula", parent=base["BodyText"], fontSize=7, leading=8.5)
    return {
        "titulo": base["Title"],
        "texto": base["Normal"],
        "secao": base["Heading3"],
        "celula": celula,
        "numero": ParagraphStyle("numero", parent=celula, alignment=2),  # 2 = direita
        "cabecalho": ParagraphStyle("cabecalho", parent=celula, fontName="Helvetica-Bold"),
    }


def _tabela(tabela, largura, estilos, texto):
    dados = [[Paragraph(escape(str(coluna)), estilos["cabecalho"]) for coluna in tabela.colunas]]
    for linha in tabela.linhas:
        dados.append([
            Paragraph(escape(texto(valor, indice in tabela.moeda)),
                      estilos["numero" if indice in tabela.moeda else "celula"])
            for indice, valor in enumerate(linha)
        ])
    if len(dados) == 1:
        dados.append([Paragraph("Nenhum registro no periodo.", estilos["celula"])]
                     + [""] * (len(tabela.colunas) - 1))
    colunas = max(len(tabela.colunas), 1)
    saida = Table(dados, colWidths=[largura / colunas] * colunas, repeatRows=1)
    saida.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), CINZA_CABECALHO),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, CINZA_LINHA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return saida


def gerar(titulo, periodo, resultado, texto):
    saida = BytesIO()
    documento = SimpleDocTemplate(
        saida, pagesize=landscape(A4), title=str(titulo),
        leftMargin=MARGEM, rightMargin=MARGEM, topMargin=MARGEM, bottomMargin=MARGEM,
    )
    estilos = _estilos()
    gerado = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    partes = [Paragraph(escape(str(titulo)), estilos["titulo"]),
              Paragraph(escape(f"{periodo} · gerado em {gerado}"), estilos["texto"]),
              Spacer(1, 4 * mm)]
    for tabela in [*resultado.resumos, resultado.principal]:
        if resultado.resumos:
            partes.append(Paragraph(escape(str(tabela.titulo)), estilos["secao"]))
        partes += [_tabela(tabela, documento.width, estilos, texto), Spacer(1, 6 * mm)]

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(doc.pagesize[0] - MARGEM, MARGEM / 2, f"Pagina {doc.page}")
        canvas.restoreState()

    documento.build(partes, onFirstPage=rodape, onLaterPages=rodape)
    return saida.getvalue()
