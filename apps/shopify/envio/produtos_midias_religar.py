"""Fotos do produto quando o vinculo dele e refeito pelo SKU (produtos_religar.py).

O produto achado na loja ja tem fotos, e os vinculos das fotos do hub apontavam para o
produto velho. Esquecer e mandar tudo duplicava a galeria; aqui cada foto do hub procura
a sua no produto achado pela referencia que o vinculo antigo guardava:

- foto que veio da loja: a URL da CDN (`shopify_src`), sem o `?v=` (midias.sem_versao);
- foto que o hub enviou: o nome do arquivo (`enviado_src`). A CDN guarda o nome do
  arquivo enviado e, se ja existe outro igual, poe um sufixo ("abc.png" -> "abc_a1b2.png").

Casou: o vinculo passa para a midia da loja e nada e reenviado. Foto da loja que nao
casou com nenhuma do hub sai (o hub e a fonte da galeria); foto do hub sem par fica sem
vinculo e o update manda (produtos_midias.pendentes). No pior caso (nenhuma referencia
bate) e o "apaga tudo e manda de novo", nunca em dobro.
"""

from apps.loja.models import MidiaProduto
from apps.shopify import midias as vinculos

MIDIAS_DA_LOJA = """query($id: ID!) {
  node(id: $id) { ... on Product { media(first: 250) {
    nodes { id ... on MediaImage { image { url } } } } } }
}"""
APAGAR = """mutation($fileIds: [ID!]!) {
  fileDelete(fileIds: $fileIds) { deletedFileIds userErrors { field message code } }
}"""


def _casa(meta, url):
    cdn = vinculos.sem_versao(meta.get("shopify_src"))
    if cdn and cdn == vinculos.sem_versao(url):
        return True
    return vinculos.e_o_arquivo(meta.get("enviado_src"), url)


def refazer(enviador, produto, produto_gid, antigos):
    """`antigos`: {pk da midia: metadata do vinculo velho}, lido antes de esquecer."""
    dados = enviador.cliente.graphql(MIDIAS_DA_LOJA, {"id": produto_gid}) or {}
    da_loja = [n for n in (((dados.get("node") or {}).get("media") or {}).get("nodes") or [])
               if (n.get("image") or {}).get("url")]
    usadas = set()
    fotos = produto.midias.filter(tipo=MidiaProduto.Tipo.IMAGEM).order_by("posicao", "id")
    for midia in fotos:
        meta = antigos.get(str(midia.pk)) or {}
        achada = next((n for n in da_loja if n["id"] not in usadas
                       and _casa(meta, n["image"]["url"])), None)
        if achada:
            usadas.add(achada["id"])
            vinculos.vincular(midia, achada["id"],
                              {**meta, "shopify_src": achada["image"]["url"]}, produto_gid)
    sobras = [n["id"] for n in da_loja if n["id"] not in usadas]
    if sobras:
        enviador.mutacao(APAGAR, {"fileIds": sobras}, "fileDelete")
