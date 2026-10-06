"""Um aviso por registro por transacao, e so depois do commit.

Importar um pedido salva o Pedido tres vezes no mesmo commit: sem isto seriam tres
avisos. Cada (conta, model, pk) vira UM aviso, com a acao combinada:

- criado + alterado = criado;
- qualquer coisa + excluido = excluido.

Mesmo desenho de apps/integracoes/envio/transacao.py: o indice fica na conexao e e
refeito quando o Django troca a lista `run_on_commit` (rollback descarta o aviso).
"""

from django.db import transaction


class AvisoPendente:
    def __init__(self, chave, aviso, enfileirar):
        self.chave = chave  # (conta, "app.model", pk)
        self.aviso = aviso
        self.enfileirar = enfileirar
        self.executado = False

    def combinar(self, aviso):
        acao_atual = self.aviso["evento"].rsplit(".", 1)[1]
        acao_nova = aviso["evento"].rsplit(".", 1)[1]
        if acao_nova == "excluido" or acao_atual != "criado":
            self.aviso = aviso
        else:
            # Continua "criado", mas com o texto mais novo (ex.: total ja calculado).
            self.aviso = {**aviso, "evento": self.aviso["evento"], "titulo": self.aviso["titulo"]}

    def __call__(self):
        self.executado = True
        self.enfileirar(self.chave[0], self.aviso)


def _indice(conexao):
    lista = conexao.run_on_commit
    guardado = getattr(conexao, "_avisos_pendentes", None)
    if guardado is None or guardado[0] is not lista:
        pendentes = {f.chave: f for _sids, f, *_ in lista if isinstance(f, AvisoPendente)}
        guardado = (lista, pendentes)
        conexao._avisos_pendentes = guardado
    return guardado[1]


def agendar(conta_id, modelo, pk, aviso, enfileirar):
    conexao = transaction.get_connection()
    chave = (str(conta_id), modelo, str(pk))
    if conexao.in_atomic_block:
        pendente = _indice(conexao).get(chave)
        if pendente is not None and not pendente.executado:
            pendente.combinar(aviso)
            return
    pendente = AvisoPendente(chave, aviso, enfileirar)
    if conexao.in_atomic_block:
        _indice(conexao)[chave] = pendente
    # robust: Redis fora do ar nao pode virar erro 500 depois que o dado ja gravou.
    transaction.on_commit(pendente, robust=True)
