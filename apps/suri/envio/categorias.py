"""Categoria do hub -> categoria do Suri Shop (arvore categoria > children).

No Suri a subcategoria vive dentro da categoria pai (`children`). Enviar uma
categoria manda a arvore inteira da raiz dela: POST se a raiz ainda nao esta no
Suri, PUT se ja esta. Cada no da arvore ganha o vinculo com o id que foi.
"""

from apps.loja.models import Categoria
from apps.suri import vinculos
from apps.suri.envio.base import RecursoSuri, id_no_suri


def raiz(categoria):
    vistas = set()
    while categoria.pai_id and categoria.pai_id not in vistas:
        vistas.add(categoria.pk)
        categoria = categoria.pai
    return categoria


def arvore(categoria, nivel=0):
    filhas = categoria.filhas.all()
    return {"id": id_no_suri("categorias", categoria), "name": categoria.nome,
            "description": categoria.descricao or "",
            # Ate 5 niveis: categoria que aponta para ela mesma nao vira laco infinito.
            "children": [arvore(f, nivel + 1) for f in filhas if f.pk != categoria.pk]
            if nivel < 5 else []}


def _vincular(categoria, no):
    vinculos.referenciar("categorias", no["id"], categoria)
    filhas = {id_no_suri("categorias", f): f for f in categoria.filhas.all()}
    for filho in no["children"]:
        if filho["id"] in filhas:
            _vincular(filhas[filho["id"]], filho)


class CategoriaSuri(RecursoSuri):
    recurso = entidade = "categorias"
    modelo = Categoria

    def garantir(self, categoria):
        """Id da categoria no Suri, enviando a arvore se ela ainda nao esta la."""
        externo = vinculos.externo_id("categorias", categoria.pk)
        return externo or self.criar(categoria)

    def _enviar_arvore(self, categoria):
        topo = raiz(categoria)
        corpo = arvore(topo)
        if vinculos.externo_id("categorias", topo.pk):
            self.cliente.put("shop/categories", corpo)
        else:
            self.cliente.post("shop/categories", corpo)
        _vincular(topo, corpo)
        return id_no_suri("categorias", categoria)

    def criar(self, obj):
        return self._enviar_arvore(obj)

    def atualizar(self, obj, external_id):
        self._enviar_arvore(obj)

    def excluir(self, external_id):
        self.cliente.delete(f"shop/categories/{external_id}")
