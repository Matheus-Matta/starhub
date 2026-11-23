from html.parser import HTMLParser

from django.db.models import CharField, Exists, F, IntegerField, OuterRef, Prefetch, Value

from apps.core.tenant.context import get_current_account_id
from apps.loja.dinheiro import texto
from apps.loja.models import ItemBundle, MidiaProduto, Produto, VarianteProduto


class _ExtratorTexto(HTMLParser):
    blocos = {"br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "p", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []

    def handle_starttag(self, tag, attrs):
        if tag in self.blocos:
            self.partes.append(" ")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in self.blocos:
            self.partes.append(" ")

    def handle_data(self, data):
        self.partes.append(data)


def _texto_publico(valor):
    extrator = _ExtratorTexto()
    extrator.feed(str(valor or ""))
    extrator.close()
    return " ".join("".join(extrator.partes).split())


def referencias_catalogo():
    conta_id = get_current_account_id()
    # Estes querysets entram como subconsultas de UNION e nao sao avaliados isoladamente;
    # o filtro explicito mantem o tenant tambem dentro de cada subconsulta.
    publicos = Produto.objects.filter(
        account_id=conta_id, active=True, status=Produto.Status.PUBLICADO
    ).exclude(
        visibilidade=Produto.Visibilidade.OCULTO
    )
    variantes = VarianteProduto.objects.filter(
        account_id=conta_id, active=True, produto__in=publicos
    ).order_by().annotate(
        nome_ordem=F("produto__nome"),
        produto_ordem=F("produto_id"),
        posicao_ordem=F("posicao"),
        tipo_linha=Value("variante", output_field=CharField()),
        objeto_id=F("id"),
    ).values(
        "nome_ordem", "produto_ordem", "posicao_ordem", "tipo_linha", "objeto_id"
    )
    variante_ativa = VarianteProduto.objects.filter(
        account_id=conta_id, active=True, produto_id=OuterRef("pk")
    )
    sem_variante = publicos.annotate(tem_variante=Exists(variante_ativa)).filter(
        tem_variante=False
    ).order_by().annotate(
        nome_ordem=F("nome"),
        produto_ordem=F("id"),
        posicao_ordem=Value(0, output_field=IntegerField()),
        tipo_linha=Value("produto", output_field=CharField()),
        objeto_id=F("id"),
    ).values(
        "nome_ordem", "produto_ordem", "posicao_ordem", "tipo_linha", "objeto_id"
    )
    return variantes.union(sem_variante).order_by(
        "nome_ordem", "produto_ordem", "posicao_ordem", "objeto_id"
    )


def _prefetch(prefixo=""):
    return (
        f"{prefixo}categorias",
        Prefetch(
            f"{prefixo}midias",
            queryset=MidiaProduto.objects.select_related("variante"),
        ),
        Prefetch(
            f"{prefixo}componentes",
            queryset=ItemBundle.objects.select_related("component_variant__produto"),
        ),
    )


def _estoque(produto, variante):
    if produto.tipo != Produto.Tipo.BUNDLE:
        if not variante:
            return "", "Nao informado"
        quantidade = variante.inventory_quantity if variante.manage_inventory else ""
        return quantidade, variante.get_stock_status_display()
    limites = [
        max(item.component_variant.inventory_quantity, 0) // max(item.quantity, 1)
        for item in produto.componentes.all()
        if item.component_variant.manage_inventory
    ]
    quantidade = min(limites) if limites else ""
    situacao = "Sem estoque" if quantidade != "" and quantidade <= 0 else "Em estoque"
    return quantidade, situacao


def _componentes(produto):
    if produto.tipo != Produto.Tipo.BUNDLE:
        return []
    itens = []
    for item in produto.componentes.all():
        variante = item.component_variant
        nome = variante.produto.nome
        if variante.produto.tipo == Produto.Tipo.VARIAVEL:
            nome = f"{nome} - {variante.titulo}"
        sku = f" ({variante.sku})" if variante.sku else ""
        itens.append(f"{item.quantity} x {nome}{sku}")
    return itens


def _linha(produto, variante, request):
    nome = produto.nome
    if variante and produto.tipo == Produto.Tipo.VARIAVEL:
        nome = f"{nome} - {variante.titulo}"
    estoque, situacao = _estoque(produto, variante)
    imagens = produto.imagens
    imagem = imagens[0]["src"] if imagens else ""
    if imagem and imagem.startswith("/"):
        imagem = request.build_absolute_uri(imagem)
    linha = {
        "nome": nome,
        "tipo": produto.get_tipo_display(),
        "variacao": variante.titulo if variante else "",
        "sku": variante.sku if variante else "",
        "preco": texto(variante.current_price) if variante else "",
        "preco_regular": texto(variante.price) if variante else "",
        "preco_promocional": texto(variante.sale_price) if variante else "",
        "estoque": estoque,
        "situacao_estoque": situacao,
        "categorias": ", ".join(categoria.nome for categoria in produto.categorias.all()),
        "componentes": _componentes(produto),
        "descricao_curta": produto.descricao_curta,
        "descricao": produto.descricao,
        "imagem": imagem,
        "url_externa": produto.url_externa,
    }
    for chave, valor in linha.items():
        if chave not in {"imagem", "url_externa"}:
            linha[chave] = (
                [_texto_publico(item) for item in valor]
                if isinstance(valor, list) else _texto_publico(valor)
            )
    return linha


def linhas_catalogo(referencias, request):
    ids_variantes = [r["objeto_id"] for r in referencias if r["tipo_linha"] == "variante"]
    ids_produtos = [r["objeto_id"] for r in referencias if r["tipo_linha"] == "produto"]
    variantes = VarianteProduto.objects.select_related("produto").prefetch_related(
        *_prefetch("produto__")
    ).filter(pk__in=ids_variantes)
    produtos = Produto.objects.prefetch_related(*_prefetch()).filter(pk__in=ids_produtos)
    por_referencia = {
        **{("variante", item.pk): (item.produto, item) for item in variantes},
        **{("produto", item.pk): (item, None) for item in produtos},
    }
    linhas = []
    for referencia in referencias:
        chave = referencia["tipo_linha"], referencia["objeto_id"]
        # Uma exclusao simultanea entre a contagem e a leitura nao deve derrubar a pagina.
        if chave in por_referencia:
            linhas.append(_linha(*por_referencia[chave], request))
    return linhas
