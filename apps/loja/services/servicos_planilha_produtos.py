"""Produtos na planilha de servicos: como a coluna `produtos` acha cada um e a aba
"Produtos" da exportacao.

achar(): SKU de uma variante, handle (slug) ou titulo, nesta ordem. A aba "Produtos"
e so consulta (a importacao le a primeira aba). Uma linha por servico e produto, com a
regra que vale para ele (a primeira ativa pela ordem, a mesma de servicos_do_produto)
e o preco do servico que ele paga:

    servico  | sku_servico | regra_ordem | produto | sku_produto | preco_produto | preco_servico
    Montagem | SERV-MONT   | 10          | Sofa    | SOF-1       | 1500,00       | 80,00
"""

from apps.integracoes.importar_planilha import LinhaInvalida
from apps.loja.models import Produto, Servico, VarianteProduto
from apps.loja.services.servicos_regras import produtos_da_regra

COLUNAS = ["servico", "sku_servico", "servico_ativo", "regra_ordem", "regra_tipo", "produto",
           "sku_produto", "preco_produto", "categorias", "preco_servico"]


def achar(texto):
    variante = VarianteProduto.objects.filter(sku=texto).select_related("produto").first()
    if variante is not None:
        return variante.produto
    produto = Produto.objects.filter(slug=texto).first()
    if produto is not None:
        return produto
    com_titulo = Produto.objects.filter(nome__iexact=texto)
    quantos = com_titulo.count()
    if quantos > 1:
        # Escolher um dos dois daria o servico ao produto errado sem ninguem ver.
        raise LinhaInvalida(f"{quantos} produtos com o titulo '{texto}'; use o SKU ou o "
                            "handle para dizer qual.")
    if not quantos:
        raise LinhaInvalida(f"produto '{texto}' nao existe no hub (procurado pelo SKU, pelo "
                            "handle e pelo titulo).")
    return com_titulo.get()


def referencia(produto):
    """SKU da variante padrao; sem SKU, o handle (achar() le os dois de volta)."""
    padrao = next((v for v in produto.variantes.all() if v.is_default), None)
    return (padrao.sku if padrao else "") or produto.slug


def linhas():
    servicos = Servico.objects.order_by("nome").prefetch_related("regras")
    for servico in servicos:
        vistos = set()
        regras = [r for r in servico.regras.order_by("ordem", "pk") if r.active]
        for regra in regras:
            produtos = produtos_da_regra(regra).prefetch_related("categorias", "variantes")
            for produto in produtos:
                if produto.pk in vistos:
                    continue  # outra regra, de ordem menor, ja deu o preco deste produto
                vistos.add(produto.pk)
                padrao = next((v for v in produto.variantes.all() if v.is_default), None)
                yield [servico.nome, servico.sku, "sim" if servico.active else "nao",
                       regra.ordem, regra.tipo, produto.nome, getattr(padrao, "sku", ""),
                       getattr(padrao, "price", None),
                       " | ".join(c.nome for c in produto.categorias.all()),
                       regra.preco if regra.preco is not None else servico.preco]


def preencher(livro, negrito):
    aba = livro.create_sheet("Produtos")
    aba.append(COLUNAS)
    for celula in aba[1]:
        celula.font = negrito
    for linha in linhas():
        aba.append(["" if valor is None else valor for valor in linha])
