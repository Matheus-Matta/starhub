"""Demo do catalogo: tags, categorias (com imagem), tipos/valores de variante e os
produtos simples (com galeria demo1/demo2 na variante padrao)."""

from decimal import Decimal

from apps.loja.demo import imagem, marca, nome_n
from apps.loja.models import Categoria, Tag, TipoVariante, ValorVariante
from apps.loja.services.midias import sincronizar_midias
from apps.loja.services.slugs import slug_livre
from apps.loja.services.variantes import criar_produto

TAGS = ["Promocao", "Lancamento", "Mais vendido", "Frete gratis", "Sustentavel", "Importado",
        "Kit", "Presente", "Inverno", "Verao"]
# (nome, pai): as filhas apontam para o pai pelo nome.
CATEGORIAS = [("Moda", None), ("Casa", None), ("Eletronicos", None),
              ("Camisetas", "Moda"), ("Calcados", "Moda"), ("Acessorios", "Moda"),
              ("Cozinha", "Casa"), ("Decoracao", "Casa"), ("Audio", "Eletronicos"),
              ("Informatica", "Eletronicos")]
TIPOS = {
    "Cor": ["Preto", "Branco", "Azul", "Vermelho"], "Tamanho": ["P", "M", "G", "GG"],
    "Numeracao": ["38", "39", "40", "41", "42"], "Material": ["Algodao", "Poliester"],
    "Voltagem": ["110V", "220V", "Bivolt"], "Capacidade": ["500 ml", "1 L"],
    "Sabor": ["Morango", "Chocolate"], "Estampa": ["Lisa", "Listrada"],
    "Acabamento": ["Fosco", "Brilho"], "Modelo": ["Basico", "Premium"],
}
# (nome, categoria, preco, promocao, estoque, marca, tags)
SIMPLES = [
    ("Camiseta basica algodao", "Camisetas", "59.90", None, 40, "Malharia Sol", [0, 4]),
    ("Tenis corrida leve", "Calcados", "299.90", "249.90", 15, "Passo Firme", [1, 2]),
    ("Bone aba curva", "Acessorios", "49.90", None, 25, "Urbano", [9]),
    ("Jogo de panelas inox", "Cozinha", "459.00", "399.00", 8, "Casa Forte", [0, 7]),
    ("Luminaria de mesa", "Decoracao", "129.90", None, 12, "Lume", [4]),
    ("Fone bluetooth", "Audio", "199.90", "179.90", 30, "Somtec", [2, 5]),
    ("Mouse sem fio", "Informatica", "79.90", None, 50, "Clikk", [3]),
    ("Teclado mecanico", "Informatica", "349.90", None, 10, "Clikk", [1, 5]),
    ("Garrafa termica", "Cozinha", "89.90", None, 0, "Casa Forte", [8]),
    ("Caixa de som portatil", "Audio", "259.90", None, 3, "Somtec", [3, 7]),
]


def tags(quantidade):
    return [Tag.objects.create(nome=nome_n(TAGS, i), metadados=marca()) for i in range(quantidade)]


def categorias(conta, quantidade):
    criadas = {}
    for i in range(max(quantidade, len(CATEGORIAS))):
        nome, pai = CATEGORIAS[i] if i < len(CATEGORIAS) else (f"Categoria extra {i + 1}", None)
        criadas[nome] = Categoria.objects.create(
            nome=nome, slug=slug_livre(Categoria, nome, conta=conta.pk), pai=criadas.get(pai),
            descricao=f"Produtos de {nome.lower()} para testar a loja.", imagem=imagem(i),
            ordem=i, exibicao="both" if pai is None else "products", metadados=marca(),
        )
    return criadas


def tipos_e_valores():
    """Tipo que a conta ja tem e reaproveitado (e nao ganha a marca: o --limpar o deixa)."""
    valores = {}
    for posicao, (nome, lista) in enumerate(TIPOS.items()):
        tipo = TipoVariante.objects.filter(nome__iexact=nome).first()
        tipo = tipo or TipoVariante.objects.create(nome=nome, posicao=posicao, metadados=marca())
        for ordem, valor in enumerate(lista):
            existente = ValorVariante.objects.filter(tipo=tipo, valor__iexact=valor).first()
            valores[(nome, valor)] = existente or ValorVariante.objects.create(
                tipo=tipo, valor=valor, posicao=ordem, metadados=marca()
            )
    return valores


def completar_produto(produto, indice, categoria, marca_nome="", tags_escolhidas=()):
    """Campos do produto que o criar_produto nao preenche, e a marca de demo."""
    produto.categoria = categoria
    produto.marca = marca_nome
    produto.descricao_curta = f"{produto.nome} para testar o StarHub."
    produto.descricao = (f"<p>{produto.nome} de demonstracao. Texto longo para ver a descricao "
                         "no admin e na API.</p>")
    produto.seo_titulo = produto.nome
    produto.destaque = indice % 4 == 0
    produto.status = "draft" if indice % 9 == 8 else "publish"
    produto.metadados = marca()
    produto.save()
    produto.categorias.set([categoria] + ([categoria.pai] if categoria.pai else []))
    produto.tags.set(tags_escolhidas)


def simples(categorias_criadas, tags_criadas, quantidade):
    produtos = []
    for i in range(quantidade):
        nome, categoria, preco, promocao, estoque, marca_nome, idx_tags = SIMPLES[i % len(SIMPLES)]
        nome = nome_n([nome], i // len(SIMPLES)) if i >= len(SIMPLES) else nome
        produto = criar_produto(
            nome, sku=f"DEMO-S{i + 1:03d}", barcode=f"7890000{i + 1:06d}", price=Decimal(preco),
            sale_price=Decimal(promocao) if promocao else None,
            compare_at_price=Decimal(preco) * 2 if i % 3 == 0 else None,
            cost=(Decimal(preco) * Decimal("0.45")).quantize(Decimal("0.01")),
            inventory_quantity=estoque, manage_inventory=True, low_stock_amount=5,
            weight=Decimal("0.5") + i,
            dimensions={"length": "20", "width": "15", "height": str(5 + i)},
            titulo="Padrao", metadados=marca(),
        )
        completar_produto(produto, i, categorias_criadas[categoria], marca_nome,
                          [tags_criadas[t % len(tags_criadas)] for t in idx_tags])
        sincronizar_midias(produto.variante_padrao, [
            {"src": imagem(i)["src"], "alt": nome},
            {"src": imagem(i + 1)["src"], "alt": f"{nome} verso"},
        ])
        produtos.append(produto)
    return produtos


def variante_de(produtos, nome):
    return next(p for p in produtos if p.nome == nome).variante_padrao

