"""Um envio por registro por transacao, e so depois do commit.

O admin salva o produto, depois as variantes, depois o produto de novo: sem isso
seriam tres tarefas iguais. Aqui cada (configuracao, recurso, pk) vira UMA tarefa,
agendada com `on_commit` (rollback nao envia nada) e com a operacao combinada:

- create + update = create (o marketplace ainda nao conhece o registro);
- qualquer coisa + delete = delete.

O indice fica na conexao e e refeito quando o Django troca a lista
`run_on_commit` (commit, rollback, rollback de savepoint): a lista e a fonte da
verdade, entao um envio descartado por rollback nunca "segura" a vaga do proximo.
"""

from django.db import transaction


class EnvioPendente:
    def __init__(self, chave, operacao, enfileirar):
        self.chave = chave  # (configuracao_id, recurso, pk)
        self.operacao = operacao
        self.enfileirar = enfileirar
        self.executado = False

    def combinar(self, operacao):
        if operacao == "delete" or self.operacao != "create":
            self.operacao = operacao

    def __call__(self):
        self.executado = True
        configuracao_id, recurso, pk = self.chave
        self.enfileirar(configuracao_id, recurso, self.operacao, pk)


def _indice(conexao):
    lista = conexao.run_on_commit
    guardado = getattr(conexao, "_envio_pendentes", None)
    if guardado is None or guardado[0] is not lista:
        pendentes = {}
        for _sids, funcao, *_resto in lista:
            if isinstance(funcao, EnvioPendente):
                pendentes[funcao.chave] = funcao
        guardado = (lista, pendentes)
        conexao._envio_pendentes = guardado
    return guardado[1]


def agendar(configuracao_id, recurso, operacao, pk, enfileirar):
    conexao = transaction.get_connection()
    chave = (str(configuracao_id), recurso, str(pk))
    if conexao.in_atomic_block:
        pendente = _indice(conexao).get(chave)
        if pendente is not None and not pendente.executado:
            pendente.combinar(operacao)
            return
    pendente = EnvioPendente(chave, operacao, enfileirar)
    if conexao.in_atomic_block:
        _indice(conexao)[chave] = pendente
    # robust: broker fora do ar nao pode virar erro 500 depois que o dado ja gravou.
    transaction.on_commit(pendente, robust=True)
