"""Demo dos produtos com mais de uma forma: variaveis (Cor x Tamanho...), kits
(bundle, estoque pelo componente que acaba primeiro) e externo (vendido fora)."""

from decimal import Decimal
from itertools import product as combinacoes

from apps.loja.demo import imagem, marca
from apps.loja.demo.catalogo import completar_produto
from apps.loja.models import ItemBundle, Produto, ValorDaVarianteProduto, VarianteProduto
from apps.loja.services.midias import sincronizar_midias
from apps.loja.services.variantes import obter_variante_padrao

# (nome, categoria, preco base, {tipo: valores}): uma variante por combinacao.
VARIAVEIS = [
    ("Camiseta estampada", "Camisetas", "79.90", {"Cor": ["Preto", "Branco"],
                                                  "Tamanho": ["P", "M", "G"]}),
    ("Tenis casual", "Calcados", "249.90", {"Numeracao": ["38", "39", "40", "41", "42"]}),
    ("Garrafa squeeze", "Cozinha", "39.90", {"Capacidade": ["500 ml", "1 L"],
                                             "Cor": ["Azul", "Vermelho"]}),
]
KITS = ["Kit home office", "Kit corrida", "Kit cozinha", "Kit presente"]
COMPONENTES_POR_KIT = 5


def variaveis(categorias_criadas, tags_criadas, valores):
    produtos = []
    for i, (nome, categoria, preco, tipos) in enumerate(VARIAVEIS):
        produto = Produto.objects.create(nome=nome, tipo=Produto.Tipo.VARIAVEL, metadados=marca())
        completar_produto(produto, i, categorias_criadas[categoria], "StarHub Demo",
                          [tags_criadas[1], tags_criadas[i % len(tags_criadas)]])
        nomes_tipos = list(tipos)
        for n, escolha in enumerate(combinacoes(*tipos.values())):
            acrescimo = Decimal("5") * (n % 3)  # tamanho/capacidade maior custa mais
            variante = VarianteProduto.objects.create(
                produto=produto, titulo=" / ".join(escolha), posicao=n,
                sku=f"DEMO-V{i + 1}-{n + 1:02d}", barcode=f"7891{i + 1:03d}{n + 1:06d}",
                price=Decimal(preco) + acrescimo, inventory_quantity=(n * 3 + 4) % 11,
                manage_inventory=True, metadados=marca(),
            )
            for tipo, valor in zip(nomes_tipos, escolha, strict=True):
                ValorDaVarianteProduto.objects.create(
                    variante=variante, valor=valores[(tipo, valor)], metadados=marca()
                )
            sincronizar_midias(variante, [{"src": imagem(n)["src"], "alt": variante.titulo}])
        produtos.append(produto)
    return produtos


def kits(categorias_criadas, simples, quantidade):
    """Kits de 5 componentes cada, ate somar `quantidade` componentes."""
    produtos = []
    for i in range(-(-quantidade // COMPONENTES_POR_KIT)):
        nome = KITS[i % len(KITS)] + ("" if i < len(KITS) else f" {i // len(KITS) + 1}")
        produto = Produto.objects.create(nome=nome, tipo=Produto.Tipo.BUNDLE, metadados=marca())
        completar_produto(produto, i, categorias_criadas["Casa"], "StarHub Demo")
        # Bundle: preco na variante unica, sem estoque proprio (vem dos componentes).
        obter_variante_padrao(produto, sku=f"DEMO-K{i + 1:02d}", price=Decimal("499.90") + i * 50,
                              titulo="Padrao", metadados=marca())
        sincronizar_midias(produto.variante_padrao, [{"src": imagem(i)["src"], "alt": nome}])
        for n in range(COMPONENTES_POR_KIT):
            componente = simples[(i * 2 + n) % len(simples)].variante_padrao
            ItemBundle.objects.create(bundle_product=produto, component_variant=componente,
                                      quantity=1 + n % 2, metadados=marca())
        produtos.append(produto)
    return produtos


def externo(categorias_criadas):
    produto = Produto.objects.create(
        nome="Curso online de fotografia", tipo=Produto.Tipo.EXTERNO, metadados=marca(),
        url_externa="https://example.com/curso-fotografia", texto_botao="Comprar no parceiro",
    )
    completar_produto(produto, 1, categorias_criadas["Informatica"], "Parceiro Demo")
    obter_variante_padrao(produto, sku="DEMO-E01", price=Decimal("197.00"), titulo="Padrao",
                          manage_inventory=False, metadados=marca())
    sincronizar_midias(produto.variante_padrao, [{"src": imagem(1)["src"], "alt": produto.nome}])
    return produto
