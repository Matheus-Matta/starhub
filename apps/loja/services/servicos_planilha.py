"""Servicos e regras em planilha: a mesma colunagem na exportacao e na importacao.

Uma linha por regra; os dados do servico se repetem em cada uma. Servico sem regra
sai numa linha com as colunas da regra vazias. Exemplo:

    sku        | nome     | preco  | ativo | regra_ordem | regra_tipo | categorias | produtos
    SERV-MONT  | Montagem | 120,00 | sim   | 10          | categoria  | Sofas      |
    SERV-MONT  | Montagem | 120,00 | sim   | 20          | produto    |            | SOF-1|SOF-2

O servico e achado pelo SKU (ou pelo nome, sem SKU) e a regra pela ordem dentro
dele: importar de novo a planilha exportada (ou a corrigida) atualiza, nunca duplica.
A exportacao traz a aba "Produtos" (servicos_planilha_produtos.py), so consulta.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from openpyxl import Workbook
from openpyxl.styles import Font

from apps.integracoes.importar_planilha import LinhaInvalida
from apps.loja.dinheiro import ValorInvalido, dinheiro
from apps.loja.models import Categoria, RegraServico, Servico
from apps.loja.services import servicos_planilha_produtos

COLUNAS = [
    ("sku", False, "SKU do servico (o codigo do ERP). Vazio: o servico e achado pelo nome."),
    ("nome", False, "Nome do servico; obrigatorio para servico novo ou sem sku."),
    ("preco", False, "Preco padrao do servico, por exemplo 120,00."),
    ("ativo", False, "sim ou nao; vazio = sim."),
    ("regra_ordem", False, "Ordem da regra (menor primeiro). Vazio: a linha mexe so no servico."),
    ("regra_tipo", False, "categoria ou produto."),
    ("regra_preco", False, "Preco do servico nesta regra; vazio = o preco padrao."),
    ("regra_ativa", False, "sim ou nao; vazio = sim."),
    ("categorias", False, "Regra por categoria: nomes separados por |."),
    ("preco_de", False, "Regra por categoria: preco do produto a partir de."),
    ("preco_ate", False, "Regra por categoria: preco do produto ate."),
    ("produtos", False, "Regra por produto: SKU, handle ou titulo de cada produto, "
                        "separados por |."),
]
EXEMPLO = ["SERV-MONT", "Montagem", "120,00", "sim", "10", "categoria", "80,00", "sim",
           "Sofas|Poltronas", "", "2000,00", ""]
SEPARADOR = "|"
SIM, NAO = {"", "sim", "s", "1", "true", "ativo", "ativa"}, {"nao", "não", "n", "0", "false"}


def _valor(dados, campo):
    bruto = str(dados.get(campo) or "").replace("R$", "").strip()
    if "," in bruto:  # "1.234,56": formato brasileiro do Excel
        bruto = bruto.replace(".", "").replace(",", ".")
    try:
        valor = dinheiro(bruto)
    except ValorInvalido as erro:
        raise LinhaInvalida(f"{campo} '{dados.get(campo)}' invalido; use 120,00.") from erro
    if valor is not None and valor < 0:
        raise LinhaInvalida(f"{campo} nao pode ser negativo.")
    return valor


def _sim(dados, campo):
    texto = str(dados.get(campo) or "").strip().casefold()
    if texto in SIM:
        return True
    if texto in NAO:
        return False
    raise LinhaInvalida(f"{campo} '{dados.get(campo)}' invalido; use sim ou nao.")


def _lista(dados, campo):
    return [p.strip() for p in str(dados.get(campo) or "").split(SEPARADOR) if p.strip()]


def _categorias(nomes):
    achadas = []
    for nome in nomes:
        categoria = (Categoria.objects.filter(nome__iexact=nome).first()
                     or Categoria.objects.filter(slug=nome).first())
        if categoria is None:
            raise LinhaInvalida(f"categoria '{nome}' nao existe; confira o nome em "
                                "Loja > Categorias.")
        achadas.append(categoria)
    return achadas


def _servico(dados):
    sku, nome = str(dados.get("sku") or "").strip(), str(dados.get("nome") or "").strip()
    if not (sku or nome):
        raise LinhaInvalida("sku e nome vazios: preencha um dos dois para achar o servico.")
    # Pelo SKU; senao pelo nome. Achado pelo nome com outro SKU na planilha, o SKU da
    # planilha vale (criar outro bateria no nome unico do servico).
    servicos = Servico.objects.select_for_update()
    servico = servicos.filter(sku=sku).first() if sku else None
    if servico is None and nome:
        servico = servicos.filter(nome_normalizado=nome.casefold()).first()
    criado = servico is None
    if criado and not nome:
        raise LinhaInvalida(f"servico {sku} nao existe: preencha o nome para criar.")
    servico = servico or Servico()
    servico.sku = sku or servico.sku
    servico.nome = nome[:150] or servico.nome
    preco = _valor(dados, "preco")
    servico.preco = preco if preco is not None else (servico.preco or Decimal("0.00"))
    servico.active = _sim(dados, "ativo")
    servico.save()
    return servico, criado


def _regra(servico, dados):
    try:
        ordem = int(str(dados["regra_ordem"]).strip())
    except ValueError as erro:
        raise LinhaInvalida(f"regra_ordem '{dados['regra_ordem']}' nao e numero.") from erro
    tipo = str(dados.get("regra_tipo") or "").strip().casefold()
    if tipo not in RegraServico.Tipo.values:
        raise LinhaInvalida("regra_tipo deve ser categoria ou produto.")
    por_produto = tipo == RegraServico.Tipo.PRODUTO
    achar = servicos_planilha_produtos.achar
    produtos = [achar(texto) for texto in _lista(dados, "produtos")] if por_produto else []
    categorias = [] if por_produto else _categorias(_lista(dados, "categorias"))
    regra = (RegraServico.objects.filter(servico=servico, ordem=ordem).first()
             or RegraServico(servico=servico, ordem=ordem))
    regra.tipo = tipo
    regra.preco, regra.active = _valor(dados, "regra_preco"), _sim(dados, "regra_ativa")
    regra.preco_de = None if por_produto else _valor(dados, "preco_de")
    regra.preco_ate = None if por_produto else _valor(dados, "preco_ate")
    try:
        regra.validar_criterios(produtos, categorias)
        regra.clean()
    except ValidationError as erro:  # o texto da regra ja diz o que fazer
        raise LinhaInvalida(" ".join(erro.messages)) from erro
    regra.save()
    regra.produtos.set(produtos)
    regra.categorias.set(categorias)


def importar_linha(dados):
    """(servico, criado) da linha; LinhaInvalida com o motivo se nao der."""
    with transaction.atomic():
        servico, criado = _servico(dados)
        if str(dados.get("regra_ordem") or "").strip():
            _regra(servico, dados)
    return servico, criado


def _sim_nao(valor):
    return "sim" if valor else "nao"


def linhas():
    """Linhas da exportacao, na ordem de COLUNAS (numero como numero no Excel)."""
    for servico in Servico.objects.order_by("nome").prefetch_related("regras"):
        base = [servico.sku, servico.nome, servico.preco, _sim_nao(servico.active)]
        regras = list(servico.regras.order_by("ordem", "pk"))
        if not regras:
            yield [*base, *[""] * (len(COLUNAS) - len(base))]
        for regra in regras:
            produtos = [servicos_planilha_produtos.referencia(p)
                        for p in regra.produtos.prefetch_related("variantes")]
            yield [*base, regra.ordem, regra.tipo, regra.preco, _sim_nao(regra.active),
                   SEPARADOR.join(regra.categorias.values_list("nome", flat=True)),
                   regra.preco_de, regra.preco_ate, SEPARADOR.join(s for s in produtos if s)]


def planilha():
    livro = Workbook()
    aba = livro.active
    aba.title = "Servicos"
    aba.append([coluna for coluna, _, _ in COLUNAS])
    for celula in aba[1]:
        celula.font = Font(bold=True)
    for linha in linhas():
        aba.append(["" if valor is None else valor for valor in linha])
    # Segunda aba, so consulta: a importacao le a primeira (apps/core/planilha.py).
    servicos_planilha_produtos.preencher(livro, Font(bold=True))
    return livro
