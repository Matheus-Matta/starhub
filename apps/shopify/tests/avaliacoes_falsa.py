"""Loja Shopify falsa para os testes de envio de avaliacoes (sem rede)."""

OK = {"userErrors": []}


class LojaFalsa:
    """Responde cada mutation pelo nome; guarda (nome, variaveis) de cada chamada."""

    def __init__(self, definicoes_existem=True):
        self.chamadas = []
        self.definicoes_existem = definicoes_existem
        self.proximo = 0

    def graphql(self, query, variables=None):
        nome = next(n for n in RESPOSTAS if n in query)
        self.chamadas.append((nome, variables))
        if nome == "fileCreate":
            self.proximo += 1
            tipo = "Video" if variables["files"][0]["contentType"] == "VIDEO" else "MediaImage"
            return {nome: {**OK, "files": [{"id": f"gid://shopify/{tipo}/{self.proximo}"}]}}
        if nome in ("metaobjectDefinitionByType", "metafieldDefinitions"):
            existe = self.definicoes_existem
            return {nome: ({"id": "gid://def/1"} if existe else None) if "ByType" in nome
                    else {"nodes": [{"id": "x"}] if existe else []}}
        return {nome: RESPOSTAS[nome](variables)}

    def nomes(self):
        return [nome for nome, _ in self.chamadas]

    def ultima(self, nome):
        return next(v for n, v in reversed(self.chamadas) if n == nome)


RESPOSTAS = {
    "metaobjectDefinitionByType": None, "metaobjectDefinitionCreate":
        lambda v: {**OK, "metaobjectDefinition": {"id": "gid://def/1"}},
    "metafieldDefinitions": None,
    "metafieldDefinitionCreate": lambda v: {**OK, "createdDefinition": {"id": "x"}},
    "metaobjectUpsert": lambda v: {**OK, "metaobject": {
        "id": f"gid://shopify/Metaobject/{v['handle']['handle']}"}},
    "metaobjectDelete": lambda v: {**OK, "deletedId": v["id"]},
    "fileCreate": None,
    "stagedUploadsCreate": lambda v: {**OK, "stagedTargets": [{
        "url": "https://upload.test/video", "resourceUrl": "https://upload.test/recurso/v",
        "parameters": [{"name": "key", "value": "abc"}]}]},
    "fileDelete": lambda v: {**OK, "deletedFileIds": v["fileIds"]},
    "metafieldsSet": lambda v: {**OK, "metafields": []},
    "metafieldsDelete": lambda v: {**OK, "deletedMetafields": []},
}
