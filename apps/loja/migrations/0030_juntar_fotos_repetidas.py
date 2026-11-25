"""Junta as linhas repetidas da galeria (a mesma imagem mais de uma vez na variante).

Webhooks simultaneos baixavam a mesma foto varias vezes (produto com 42 linhas e 14
imagens). Nenhum arquivo e apagado e nada e enviado as lojas: so a linha repetida sai
da galeria, e fica anotada em `metadados["fotos_repetidas"]` da que permanece.

- Igual = mesmo conteudo do arquivo, no mesmo produto E variante. Parecida nao conta.
- A mesma imagem em duas variantes continua nas duas, com a MESMA url: os envios ja
  tratam url igual como uma foto so.
- Os vinculos com as lojas passam para a linha que fica. Sem isso o proximo update do
  Shopify apagaria a foto de la (vinculo sem linha = foto excluida no hub) e a
  importacao baixaria outra copia.

Voltar a migracao recria as linhas anotadas; os vinculos ficam onde estao.
"""

import logging
from collections import defaultdict

from django.db import migrations

from apps.core.imagens_iguais import identidade

logger = logging.getLogger(__name__)
CHAVE = "fotos_repetidas"


def _apontar(Referencia, origem, destino, url):
    """Leva os vinculos de `origem` para `destino`, que usa `url`."""
    vinculos = Referencia._base_manager.filter(
        account_id=origem.account_id, entity_type="midias", object_id=str(origem.pk))
    for vinculo in list(vinculos):
        vinculo.object_id = str(destino.pk)
        # Foto enviada pelo hub: `enviado_src` diferente da url seria lido como foto
        # trocada, e o envio apagaria a da loja para mandar de novo.
        if isinstance(vinculo.metadata, dict) and vinculo.metadata.get("enviado_src"):
            vinculo.metadata = {**vinculo.metadata, "enviado_src": url}
        vinculo.save(update_fields=["object_id", "metadata"])


def _anotar(fica, sai):
    meta = fica.metadados if isinstance(fica.metadados, dict) else {}
    fica.metadados = {**meta, CHAVE: [*meta.get(CHAVE, []), *(
        {"variante_id": m.variante_id, "url": m.url, "alt_text": m.alt_text,
         "posicao": m.posicao, "origin": m.origin} for m in sai)]}


def _juntar_produto(linhas, com_vinculo, Referencia):
    """Devolve quantas linhas repetidas sairam."""
    por_imagem, removidas = defaultdict(list), 0
    for midia in linhas:
        por_imagem[identidade(midia.url)].append(midia)
    for iguais in por_imagem.values():
        if len(iguais) < 2:
            continue
        # A ligada a uma loja fica (as outras sao as copias orfas); empate, a primeira.
        iguais.sort(key=lambda m: (str(m.pk) not in com_vinculo, m.posicao, m.pk))
        url, por_variante = iguais[0].url, defaultdict(list)
        for midia in iguais:
            por_variante[midia.variante_id].append(midia)
        for fica, *sai in por_variante.values():
            for midia in (*sai, *([fica] if fica.url != url else [])):
                _apontar(Referencia, midia, fica, url)
            if sai:
                _anotar(fica, sai)
            fica.posicao = min(m.posicao for m in (fica, *sai))  # a capa segue capa
            fica.url = url
            fica.save(update_fields=["url", "posicao", "metadados"])
            for midia in sai:
                midia.delete()
                removidas += 1
    return removidas


def juntar(apps, schema_editor):
    Midia = apps.get_model("loja", "MidiaProduto")
    Referencia = apps.get_model("core", "ExternalReference")
    com_vinculo = set(Referencia._base_manager.filter(entity_type="midias")
                      .values_list("object_id", flat=True))
    grupos = defaultdict(list)
    for midia in Midia._base_manager.filter(tipo="image").order_by("posicao", "id"):
        grupos[midia.produto_id].append(midia)
    total = produtos = 0
    for linhas in grupos.values():
        removidas = _juntar_produto(linhas, com_vinculo, Referencia)
        total += removidas
        produtos += bool(removidas)
    logger.warning("Fotos repetidas: %s linhas juntadas em %s produtos; nenhum arquivo "
                   "apagado.", total, produtos)


def recriar(apps, schema_editor):
    Midia = apps.get_model("loja", "MidiaProduto")
    for fica in list(Midia._base_manager.exclude(metadados=[])):
        if not isinstance(fica.metadados, dict) or CHAVE not in fica.metadados:
            continue
        for dados in fica.metadados[CHAVE]:
            Midia._base_manager.create(account_id=fica.account_id, produto_id=fica.produto_id,
                                       tipo=fica.tipo, **dados)
        resto = {k: v for k, v in fica.metadados.items() if k != CHAVE}
        fica.metadados = resto or []
        fica.save(update_fields=["metadados"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_catalogo_publico"),
        ("loja", "0029_fdc_nas_integracoes_ignoradas"),
        # Os dados do Shopify precisam ja estar no vinculo.
        ("shopify", "0001_midias_no_vinculo"),
    ]

    operations = [migrations.RunPython(juntar, recriar)]
